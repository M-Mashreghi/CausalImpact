"""Classical two-way fixed-effects event study, as a *diagnostic baseline* (Task 4.4).

    Y_it = a_i + l_t + sum_{k != ref} b_k 1[t - G_i = k] + e_it

with G_i the unit's treatment start, never-treated units contributing only to the
fixed effects, and relative time ``ref`` (default -1) omitted as the reference.
Relative times outside ``window`` are binned into the end points. Standard errors are
CR1 cluster-robust by unit.

With staggered adoption and heterogeneous effects the b_k are contaminated by effects
from other relative times (Sun & Abraham 2021); the result is then flagged and must not
be reported as dynamic treatment effects. The heterogeneity-robust estimator is Task 4.8.
Requires a balanced panel (exact two-way demeaning).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.estimators.ols import ols_cluster_robust, two_way_demean
from causalimpact.panel.contract import PanelSpec, validate_panel

NAME = "event_study_twfe"


def relative_time(data: pd.DataFrame, spec: PanelSpec) -> pd.Series:
    """t - G_i for ever-treated units; NaN for never-treated units."""
    return data[spec.period] - data[spec.treatment_start]


def twfe_event_study(
    data: pd.DataFrame,
    spec: PanelSpec,
    *,
    window: tuple[int, int] | None = None,
    reference: int = -1,
    confidence_level: float = 0.95,
) -> DiagnosticResult:
    result, timing = validate_panel(data, spec)
    if result.is_blocking or timing is None:
        raise ValueError(f"panel timing is invalid: {sorted(result.codes())}")
    if not timing.balanced or data[spec.outcome].isna().any():
        raise ValueError("the TWFE event study needs a balanced panel without gaps")
    if timing.n_never_treated == 0 and not timing.is_staggered:
        raise ValueError(
            "a single cohort without never-treated units cannot separate relative time from "
            "calendar time"
        )

    rel = relative_time(data, spec)
    if window is not None:
        lo, hi = window
        if not lo <= reference <= hi:
            raise ValueError("the reference period must lie inside the window")
        rel = rel.clip(lower=lo, upper=hi)
    levels = sorted(int(k) for k in rel.dropna().unique() if k != reference)
    if reference not in set(rel.dropna().astype(int)):
        raise ValueError(f"reference relative time {reference} is not observed")
    dummies = np.column_stack([(rel == k).to_numpy(dtype=float) for k in levels])
    unit = data[spec.unit].to_numpy()
    period = data[spec.period].to_numpy()
    x = two_way_demean(dummies, unit, period)
    y = two_way_demean(data[spec.outcome].to_numpy(dtype=float), unit, period)
    fit = ols_cluster_robust(x, y, unit)
    se = np.sqrt(np.diag(fit.cov))
    n_clusters = len(np.unique(unit))
    crit = float(stats.t.ppf(0.5 + confidence_level / 2, n_clusters - 1))
    counts = rel.value_counts()

    rows: dict[int, JsonValue] = {
        reference: {
            "relative_time": reference,
            "coef": 0.0,
            "std_error": None,
            "ci_lower": None,
            "ci_upper": None,
            "n_obs": int(counts.get(reference, 0)),
            "reference": True,
        }
    }
    for k, b, s in zip(levels, fit.coef, se, strict=True):
        rows[k] = {
            "relative_time": k,
            "coef": float(b),
            "std_error": float(s),
            "ci_lower": float(b - crit * s),
            "ci_upper": float(b + crit * s),
            "n_obs": int(counts.get(k, 0)),
            "reference": False,
            "binned_endpoint": window is not None and k in window,
        }
    coefficients: list[JsonValue] = [rows[k] for k in sorted(rows)]

    findings: list[Finding] = []
    if timing.is_staggered:
        findings.append(
            Finding(
                code="twfe_event_study_staggered",
                severity=FindingSeverity.WARNING,
                message=(
                    "staggered adoption: TWFE relative-time coefficients are contaminated by "
                    "effects at other relative times when effects are heterogeneous (Sun & "
                    "Abraham 2021). Diagnostic only; use the heterogeneity-robust event study."
                ),
            )
        )
    metrics: dict[str, JsonValue] = {
        "label": "diagnostic baseline, not a causal dynamic-effect estimate",
        "reference_relative_time": reference,
        "window": list(window) if window else None,
        "confidence_level": confidence_level,
        "inference": "CR1 clustered by unit, t with G-1 df",
        "n_clusters": n_clusters,
        "staggered": timing.is_staggered,
        "coefficients": coefficients,
        # Covariance of the estimated (non-reference) coefficients, in this order;
        # used by the joint pre-trend test.
        "coefficient_order": list(levels),
        "covariance": [[float(v) for v in row] for row in fit.cov],
    }
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics)
