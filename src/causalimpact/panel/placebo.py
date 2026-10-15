"""Placebo / falsification tests for policy workflows (Task 4.10).

* **In-space** (synthetic control): every donor is treated as if it were the treated
  unit. The treated unit's post/pre RMSPE ratio is ranked among all units; the rank-based
  p-value is reported together with the whole placebo distribution and the smallest
  attainable p-value. If the treated unit is not extreme, the effect is not
  distinguishable from what donors show without treatment.
* **In-time**: the treatment date is moved to a fake period inside the pre-treatment
  window, using only pre-treatment data. A sizeable "effect" at a date when nothing
  happened undermines the design. Hooks exist for synthetic control and for the
  single-cohort DiD.

Placebo results are falsification evidence. Passing them does not prove the design is
valid, and the reports say so; a rank p-value from J donors cannot be smaller than
1/(J+1).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import JsonValue

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.estimands import Estimand
from causalimpact.estimators.base import run_estimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.multi_period import SingleCohortDiD
from causalimpact.panel.synthetic_control import (
    SyntheticControl,
    fit_synthetic,
    in_space_placebos,
)

CAVEAT = (
    "placebo tests are falsification checks: passing them does not prove the design is "
    "valid, and failing them does not identify which assumption is wrong"
)


def in_space_placebo_test(
    data: pd.DataFrame,
    spec: PanelSpec | None = None,
    *,
    alpha: float = 0.1,
    prefit_cutoff: float = 5.0,
) -> DiagnosticResult:
    sc = SyntheticControl(spec or PanelSpec())
    wide, treated, t0, donors, _ = sc.prepare(data)
    fit = fit_synthetic(wide, treated, donors, t0)
    runs = in_space_placebos(wide, donors, t0)
    table: list[JsonValue] = [
        {
            "unit": r.unit,
            "pre_rmspe": r.fit.pre_rmspe,
            "post_rmspe": r.fit.post_rmspe,
            "rmspe_ratio": r.fit.rmspe_ratio,
            "att": r.fit.att,
            "comparable_prefit": r.fit.pre_rmspe <= prefit_cutoff * fit.pre_rmspe,
        }
        for r in runs
    ]
    ratios = np.array([r.fit.rmspe_ratio for r in runs])
    rank = int(np.sum(ratios >= fit.rmspe_ratio) + 1)
    p_value = rank / (len(runs) + 1)
    min_p = 1 / (len(runs) + 1)
    findings: list[Finding] = []
    if min_p > alpha:
        findings.append(
            Finding(
                code="insufficient_placebos",
                severity=FindingSeverity.WARNING,
                message=f"{len(runs)} donors: the smallest attainable p-value is {min_p:.3f} "
                f"> {alpha:g}",
            )
        )
    if p_value > alpha:
        findings.append(
            Finding(
                code="effect_not_extreme_among_placebos",
                severity=FindingSeverity.WARNING,
                message=f"the treated unit ranks {rank} of {len(runs) + 1} by post/pre RMSPE "
                f"ratio (p = {p_value:.3f}); the effect is not distinguishable from placebo "
                "units that were not treated",
            )
        )
    metrics: dict[str, JsonValue] = {
        "treated_unit": treated,
        "treatment_period": t0,
        "treated_rmspe_ratio": fit.rmspe_ratio,
        "treated_att": fit.att,
        "rank": rank,
        "n_units": len(runs) + 1,
        "p_value": p_value,
        "minimum_attainable_p_value": min_p,
        "alpha": alpha,
        "placebos": table,
    }
    return DiagnosticResult(
        name="placebo_in_space", findings=tuple(findings), metrics=metrics, notes=(CAVEAT,)
    )


def _fake_treatment(data: pd.DataFrame, spec: PanelSpec, fake_period: int) -> pd.DataFrame:
    starts = data.groupby(spec.unit)[spec.treatment_start].first()
    treated = starts.dropna()
    if treated.empty:
        raise ValueError("no treated units")
    real = int(treated.min())
    if not data[spec.period].min() < fake_period < real:
        raise ValueError("the fake period must lie strictly inside the pre-treatment window")
    pre = data[data[spec.period] < real].copy()
    is_treated = pre[spec.treatment_start].notna()
    pre.loc[is_treated, spec.treatment_start] = float(fake_period)
    return pre


def in_time_placebo_test(
    data: pd.DataFrame,
    fake_period: int,
    spec: PanelSpec | None = None,
    *,
    tolerance: float = 0.5,
) -> DiagnosticResult:
    """Synthetic control re-run with a fake treatment date on pre-treatment data only.

    Flags the design when the placebo gap is at least ``tolerance`` times the real
    estimated effect (or, if that is ~0, when the placebo is large relative to fit).
    """
    s = spec or PanelSpec()
    sc = SyntheticControl(s)
    wide, treated, t0, donors, _ = sc.prepare(data)
    real = fit_synthetic(wide, treated, donors, t0)
    fake = _fake_treatment(data, s, fake_period)
    f_wide, f_treated, f_t0, f_donors, _ = sc.prepare(fake)
    placebo = fit_synthetic(f_wide, f_treated, f_donors, f_t0)
    threshold = tolerance * max(abs(real.att), 1e-12)
    findings: list[Finding] = []
    if abs(placebo.att) >= threshold:
        findings.append(
            Finding(
                code="in_time_placebo_effect",
                severity=FindingSeverity.WARNING,
                message=f"a fake treatment in period {fake_period} produces a gap of "
                f"{placebo.att:.3g}, at least {tolerance:g}x the estimated effect "
                f"({real.att:.3g}); the counterfactual may not be credible",
            )
        )
    metrics: dict[str, JsonValue] = {
        "fake_period": fake_period,
        "placebo_att": placebo.att,
        "placebo_rmspe_ratio": placebo.rmspe_ratio,
        "real_att": real.att,
        "tolerance": tolerance,
    }
    return DiagnosticResult(
        name="placebo_in_time", findings=tuple(findings), metrics=metrics, notes=(CAVEAT,)
    )


def did_in_time_placebo(
    data: pd.DataFrame,
    estimand: Estimand,
    fake_period: int,
    spec: PanelSpec | None = None,
    *,
    alpha: float = 0.05,
) -> DiagnosticResult:
    """Single-cohort DiD on pre-treatment data with a fake adoption date."""
    s = spec or PanelSpec()
    fake = _fake_treatment(data, s, fake_period)
    est = run_estimator(SingleCohortDiD(s), fake, estimand)
    findings: list[Finding] = []
    if est.p_value is not None and est.p_value < alpha:
        findings.append(
            Finding(
                code="in_time_placebo_effect",
                severity=FindingSeverity.WARNING,
                message=f"a fake adoption in period {fake_period} yields a significant "
                f"'effect' {est.estimate:.3g} (p = {est.p_value:.3g}); parallel trends are "
                "doubtful",
            )
        )
    metrics: dict[str, JsonValue] = {
        "fake_period": fake_period,
        "placebo_estimate": est.estimate,
        "ci": [est.ci_lower, est.ci_upper],
        "p_value": est.p_value,
    }
    return DiagnosticResult(
        name="placebo_in_time_did", findings=tuple(findings), metrics=metrics, notes=(CAVEAT,)
    )
