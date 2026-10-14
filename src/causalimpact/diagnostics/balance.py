"""Covariate balance by arm via standardized mean differences.

SMD = (mean_treated - mean_control) / sqrt((s2_treated + s2_control) / 2)

with sample variances (ddof=1) for numeric covariates and p(1 - p) for binary
covariates and categorical-level indicators (Austin, 2009). No hypothesis tests are run:
in a randomized experiment any imbalance is chance by construction, so balance p-values
are not a randomization-validity gate. Large SMDs are surfaced descriptively.
"""

from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity, examples
from causalimpact.domain.variables import CovariateDType, CovariateSpec

DEFAULT_SMD_THRESHOLD = 0.1
Kind = Literal["numeric", "binary"]


class BalanceRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    covariate: str
    level: str | None
    comparison: str
    mean_treated: float | None
    mean_control: float | None
    sd_treated: float | None
    sd_control: float | None
    smd: float | None
    n_treated: int
    n_control: int
    missing_treated: int
    missing_control: int


def _moments(x: np.ndarray, kind: Kind) -> tuple[float | None, float | None]:
    if x.size == 0:
        return None, None
    mean = float(x.mean())
    if kind == "binary":
        return mean, mean * (1.0 - mean)
    return mean, float(x.var(ddof=1)) if x.size > 1 else None


def standardized_mean_difference(
    treated: np.ndarray, control: np.ndarray, kind: Kind = "numeric"
) -> float | None:
    """SMD of two samples (missing values must already be removed).

    Returns ``None`` when undefined (empty arm, or zero pooled variance with different
    means); returns 0.0 for identical constants.
    """
    m_t, v_t = _moments(treated, kind)
    m_c, v_c = _moments(control, kind)
    if m_t is None or m_c is None or v_t is None or v_c is None:
        return None
    pooled = math.sqrt((v_t + v_c) / 2.0)
    if pooled == 0.0:
        return 0.0 if m_t == m_c else None
    return (m_t - m_c) / pooled


def _row(
    covariate: str,
    level: str | None,
    comparison: str,
    t: pd.Series,
    c: pd.Series,
    kind: Kind,
) -> BalanceRow:
    t_vals = t.dropna().to_numpy(dtype=float)
    c_vals = c.dropna().to_numpy(dtype=float)
    m_t, v_t = _moments(t_vals, kind)
    m_c, v_c = _moments(c_vals, kind)
    return BalanceRow(
        covariate=covariate,
        level=level,
        comparison=comparison,
        mean_treated=m_t,
        mean_control=m_c,
        sd_treated=None if v_t is None else math.sqrt(v_t),
        sd_control=None if v_c is None else math.sqrt(v_c),
        smd=standardized_mean_difference(t_vals, c_vals, kind),
        n_treated=int(t_vals.size),
        n_control=int(c_vals.size),
        missing_treated=int(t.isna().sum()),
        missing_control=int(c.isna().sum()),
    )


def _indicator(column: pd.Series, level: str) -> pd.Series:
    """0/1 indicator of ``level``, keeping missing values missing."""
    return (column.astype(str) == level).astype(float).where(column.notna())


def balance_table(
    data: pd.DataFrame,
    arm_column: str,
    control_arm: str,
    covariates: tuple[CovariateSpec, ...],
) -> list[BalanceRow]:
    """Balance rows for every non-control arm against the control arm."""
    arms = [a for a in pd.unique(data[arm_column].dropna()) if a != control_arm]
    control = data.loc[data[arm_column] == control_arm]
    rows: list[BalanceRow] = []
    for arm in sorted(map(str, arms)):
        treated = data.loc[data[arm_column].astype(str) == arm]
        comparison = f"{arm} vs {control_arm}"
        for cov in covariates:
            if cov.dtype is CovariateDType.CATEGORICAL:
                levels = sorted(data[cov.name].dropna().astype(str).unique())
                for level in levels:
                    rows.append(
                        _row(
                            cov.name,
                            level,
                            comparison,
                            _indicator(treated[cov.name], level),
                            _indicator(control[cov.name], level),
                            "binary",
                        )
                    )
            else:
                kind: Kind = "binary" if cov.dtype is CovariateDType.BINARY else "numeric"
                rows.append(
                    _row(cov.name, None, comparison, treated[cov.name], control[cov.name], kind)
                )
    return rows


def summarize_balance(
    name: str,
    rows: list[BalanceRow],
    *,
    threshold: float,
    imbalance_message: str,
) -> DiagnosticResult:
    findings: list[Finding] = []
    flagged = [r for r in rows if r.smd is not None and abs(r.smd) > threshold]
    if flagged:
        findings.append(
            Finding(
                code="smd_above_threshold",
                severity=FindingSeverity.WARNING,
                message=imbalance_message,
                count=len(flagged),
                examples=examples(
                    f"{r.covariate}{'=' + r.level if r.level else ''} ({r.comparison}): {r.smd:.3f}"
                    for r in flagged
                    if r.smd is not None
                ),
            )
        )
    undefined = [r for r in rows if r.smd is None]
    if undefined:
        findings.append(
            Finding(
                code="smd_undefined",
                severity=FindingSeverity.WARNING,
                message="SMD undefined (empty arm or zero variance with differing means)",
                count=len(undefined),
                examples=examples(r.covariate for r in undefined),
            )
        )
    smds = [abs(r.smd) for r in rows if r.smd is not None]
    metrics = {
        "threshold": threshold,
        "max_abs_smd": max(smds) if smds else None,
        "n_rows": len(rows),
        "n_above_threshold": len(flagged),
        "table": [r.model_dump(mode="json") for r in rows],
    }
    return DiagnosticResult(name=name, findings=tuple(findings), metrics=metrics)


def _weighted_mean(x: np.ndarray, w: np.ndarray) -> float | None:
    total = float(w.sum())
    return float(np.dot(w, x) / total) if total > 0 else None


def _weighted_row(
    covariate: str,
    level: str | None,
    comparison: str,
    values: pd.Series,
    treated: np.ndarray,
    weights: np.ndarray,
    kind: Kind,
) -> BalanceRow:
    """Weighted SMD with the denominator from the *unweighted* arm variances.

    Holding the denominator fixed means a change in SMD reflects a change in the weighted
    means only, which is the standard convention for comparing balance before and after
    matching or weighting.
    """
    present = values.notna().to_numpy()
    x = values.to_numpy(dtype=float)
    t_mask, c_mask = present & treated, present & ~treated
    _, v_t = _moments(x[t_mask], kind)
    _, v_c = _moments(x[c_mask], kind)
    m_t = _weighted_mean(x[t_mask], weights[t_mask])
    m_c = _weighted_mean(x[c_mask], weights[c_mask])
    smd: float | None = None
    if m_t is not None and m_c is not None and v_t is not None and v_c is not None:
        pooled = math.sqrt((v_t + v_c) / 2.0)
        if pooled > 0:
            smd = (m_t - m_c) / pooled
        elif m_t == m_c:
            smd = 0.0
    return BalanceRow(
        covariate=covariate,
        level=level,
        comparison=comparison,
        mean_treated=m_t,
        mean_control=m_c,
        sd_treated=None if v_t is None else math.sqrt(v_t),
        sd_control=None if v_c is None else math.sqrt(v_c),
        smd=smd,
        n_treated=int(np.sum(t_mask & (weights > 0))),
        n_control=int(np.sum(c_mask & (weights > 0))),
        missing_treated=int(np.sum(~present & treated)),
        missing_control=int(np.sum(~present & ~treated)),
    )


def weighted_balance_rows(
    data: pd.DataFrame,
    treated: np.ndarray,
    weights: np.ndarray,
    covariates: tuple[CovariateSpec, ...],
    comparison: str,
) -> list[BalanceRow]:
    """Balance rows for a two-group comparison under unit weights (matching / weighting)."""
    t = np.asarray(treated, dtype=bool)
    w = np.asarray(weights, dtype=float)
    if w.shape != t.shape or np.any(w < 0) or not np.all(np.isfinite(w)):
        raise ValueError("weights must be finite, non-negative and aligned with units")
    rows: list[BalanceRow] = []
    for cov in covariates:
        column = data[cov.name]
        if cov.dtype is CovariateDType.CATEGORICAL:
            for level in sorted(column.dropna().astype(str).unique()):
                indicator = _indicator(column, level)
                rows.append(_weighted_row(cov.name, level, comparison, indicator, t, w, "binary"))
        else:
            kind: Kind = "binary" if cov.dtype is CovariateDType.BINARY else "numeric"
            rows.append(_weighted_row(cov.name, None, comparison, column, t, w, kind))
    return rows
