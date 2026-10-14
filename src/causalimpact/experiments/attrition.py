"""Attrition and missing-outcome diagnostics (Task 2.10).

A randomization unit has *attrited* when it is absent from the analysis data or all of its
outcome values are missing. Attrition that differs by arm breaks the comparability that
randomization provided, so the ITT on observed units may be biased.

Differential attrition is blocking when it is statistically detectable (chi-square test
of independence, arm x attrited, at ``alpha``) *or* when the largest absolute difference
in attrition rates exceeds the declared ``max_rate_difference``. It stays blocking until a
resolution (e.g. a bounds analysis or a documented logging explanation) is recorded, at
which point it is reported as a resolved warning. It is never dropped.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.experiments.spec import ExperimentSpec

NAME = "attrition"


def _attrited_units(
    spec: ExperimentSpec, assignments: pd.DataFrame, analysis: pd.DataFrame, outcome: str
) -> pd.DataFrame:
    rand, arm = spec.randomization_unit, spec.arm_column
    units = assignments.dropna(subset=[rand, arm]).drop_duplicates(subset=[rand])
    observed = analysis.loc[analysis[outcome].notna(), rand].unique()
    return units.assign(_attrited=~units[rand].isin(observed))


def _rates(frame: pd.DataFrame, arm: str) -> pd.DataFrame:
    grouped = frame.groupby(arm)["_attrited"].agg(["size", "sum"])
    grouped.columns = ["n_assigned", "n_attrited"]
    grouped["attrition_rate"] = grouped["n_attrited"] / grouped["n_assigned"]
    return grouped


def check_attrition(
    spec: ExperimentSpec,
    assignments: pd.DataFrame,
    analysis: pd.DataFrame,
    outcome: str,
    *,
    alpha: float = 0.05,
    max_rate_difference: float = 0.01,
    max_overall_rate: float = 0.2,
    period_column: str | None = None,
    resolution: str | None = None,
) -> DiagnosticResult:
    rand, arm = spec.randomization_unit, spec.arm_column
    for frame, cols, label in (
        (assignments, [rand, arm], "assignments"),
        (analysis, [rand, outcome], "analysis data"),
    ):
        if missing := [c for c in cols if c not in frame]:
            raise ValueError(f"{label} is missing columns {missing}")
    if period_column is not None and period_column not in assignments:
        raise ValueError(f"assignments are missing period column {period_column!r}")

    units = _attrited_units(spec, assignments, analysis, outcome)
    rates = _rates(units, arm)
    overall = float(units["_attrited"].mean())
    findings: list[Finding] = []

    table = pd.crosstab(units[arm], units["_attrited"]).reindex(columns=[False, True], fill_value=0)
    p_value: float | None = None
    if len(table) >= 2 and table[True].sum() > 0 and table[False].sum() > 0:
        p_value = float(stats.chi2_contingency(table.to_numpy(), correction=False).pvalue)
    pairs = combinations(rates.index, 2)
    max_diff = max(
        (abs(rates.loc[a, "attrition_rate"] - rates.loc[b, "attrition_rate"]) for a, b in pairs),
        default=0.0,
    )
    differential = (p_value is not None and p_value < alpha) or max_diff > max_rate_difference
    if differential:
        detail = (
            f"attrition rates differ by arm (max difference {max_diff:.4f}, "
            f"chi-square p={p_value if p_value is None else f'{p_value:.3g}'})"
        )
        if resolution is None:
            findings.append(
                Finding(
                    code="differential_attrition",
                    severity=FindingSeverity.BLOCKING,
                    message=detail + "; ITT on observed units may be biased. Record a "
                    "resolution (e.g. bounds analysis) before issuing a decision label.",
                    count=int(units["_attrited"].sum()),
                )
            )
        else:
            findings.append(
                Finding(
                    code="differential_attrition_resolved",
                    severity=FindingSeverity.WARNING,
                    message=f"{detail}; resolution recorded: {resolution}",
                    count=int(units["_attrited"].sum()),
                )
            )
    if overall > max_overall_rate:
        findings.append(
            Finding(
                code="high_overall_attrition",
                severity=FindingSeverity.WARNING,
                message=f"overall attrition {overall:.3f} exceeds {max_overall_rate:g}",
                count=int(units["_attrited"].sum()),
            )
        )

    metrics: dict[str, JsonValue] = {
        "outcome": outcome,
        "overall_attrition_rate": overall,
        "max_rate_difference": float(max_diff),
        "tolerance": max_rate_difference,
        "chi_square_p_value": p_value,
        "alpha": alpha,
        "by_arm": {
            str(k): {
                "n_assigned": int(r.n_assigned),
                "n_attrited": int(r.n_attrited),
                "attrition_rate": float(r.attrition_rate),
            }
            for k, r in rates.iterrows()
        },
    }
    if period_column is not None:
        by_period: list[JsonValue] = []
        flagged = []
        for period, group in units.groupby(period_column, sort=True):
            period_rates = _rates(group, arm)
            spread = float(np.ptp(period_rates["attrition_rate"])) if len(period_rates) > 1 else 0.0
            by_period.append(
                {
                    "period": str(period),
                    "rates": {str(k): float(v) for k, v in period_rates["attrition_rate"].items()},
                    "max_rate_difference": spread,
                }
            )
            if spread > max_rate_difference:
                flagged.append(str(period))
        metrics["by_period"] = by_period
        if flagged:
            findings.append(
                Finding(
                    code="differential_attrition_period",
                    severity=FindingSeverity.WARNING,
                    message="attrition differs by arm within some assignment periods",
                    count=len(flagged),
                    examples=tuple(flagged[:5]),
                )
            )
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics)
