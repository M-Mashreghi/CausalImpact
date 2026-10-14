"""Panel data contract and treatment-timing model (Task 4.1).

A panel has one row per (unit, period). Treatment timing is described by each unit's
``treatment_start`` period (missing = never treated within the data). v1 supports
*absorbing* treatment only: once treated, a unit stays treated. Non-absorbing patterns
are refused rather than silently re-coded.

Timing problems that invalidate DiD comparisons (duplicate rows, start periods that vary
within a unit, indicators inconsistent with the start, treatment switching off) are
blocking. Features that restrict what can be estimated (unbalanced panel, units treated
before the first observed period, starts after the last period) are surfaced as warnings.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, JsonValue

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.types import NonBlankStr

NAME = "panel_timing"


class PanelSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    unit: NonBlankStr = "unit_id"
    period: NonBlankStr = "period"
    outcome: NonBlankStr = "outcome"
    treatment_start: NonBlankStr = "treatment_start"
    treated: NonBlankStr | None = None
    cluster: NonBlankStr | None = None
    covariates: tuple[NonBlankStr, ...] = ()


@dataclass(frozen=True)
class PanelTiming:
    periods: tuple[int, ...]
    cohorts: dict[int, int]  # treatment start period -> number of units
    n_units: int
    n_never_treated: int
    n_always_treated: int
    balanced: bool

    @property
    def is_staggered(self) -> bool:
        return len(self.cohorts) > 1

    def to_json(self) -> dict[str, JsonValue]:
        return {
            "periods": list(self.periods),
            "cohorts": {str(k): v for k, v in self.cohorts.items()},
            "n_units": self.n_units,
            "n_never_treated": self.n_never_treated,
            "n_always_treated": self.n_always_treated,
            "balanced": self.balanced,
            "staggered": self.is_staggered,
        }


def _finding(
    code: str, blocking: bool, message: str, ids: Iterable[object] | None = None
) -> Finding:
    unique = sorted({str(i) for i in ids}) if ids is not None else []
    return Finding(
        code=code,
        severity=FindingSeverity.BLOCKING if blocking else FindingSeverity.WARNING,
        message=message,
        count=len(unique) or 1,
        examples=tuple(unique[:5]),
    )


def validate_panel(
    df: pd.DataFrame, spec: PanelSpec
) -> tuple[DiagnosticResult, PanelTiming | None]:
    required = [spec.unit, spec.period, spec.outcome, spec.treatment_start]
    required += [c for c in (spec.treated, spec.cluster) if c is not None]
    required += list(spec.covariates)
    if missing := [c for c in dict.fromkeys(required) if c not in df]:
        result = DiagnosticResult(
            name=NAME,
            findings=(_finding("missing_column", True, f"panel is missing columns {missing}"),),
        )
        return result, None

    findings: list[Finding] = []
    u, p, s = spec.unit, spec.period, spec.treatment_start
    if df[u].isna().any() or df[p].isna().any():
        findings.append(_finding("missing_unit_or_period", True, "unit or period is missing"))
        return DiagnosticResult(name=NAME, findings=tuple(findings)), None
    periods = df[p]
    if not pd.api.types.is_numeric_dtype(periods) or not np.all(np.mod(periods, 1) == 0):
        findings.append(_finding("non_integer_period", True, "periods must be integers"))
        return DiagnosticResult(name=NAME, findings=tuple(findings)), None
    starts = df[s]
    present_starts = starts.dropna()
    if not pd.api.types.is_numeric_dtype(starts) or not np.all(np.mod(present_starts, 1) == 0):
        findings.append(
            _finding("non_integer_start", True, "treatment_start must be an integer period")
        )
        return DiagnosticResult(name=NAME, findings=tuple(findings)), None

    dup = df.duplicated(subset=[u, p], keep=False)
    if dup.any():
        findings.append(
            _finding("duplicate_unit_period", True, "duplicate (unit, period) rows", df.loc[dup, u])
        )
    per_unit_starts = df.groupby(u)[s].apply(lambda x: x.fillna(-np.inf).nunique())
    varying = per_unit_starts[per_unit_starts > 1]
    if len(varying):
        findings.append(
            _finding(
                "inconsistent_start",
                True,
                "treatment_start varies within a unit",
                varying.index,
            )
        )

    post = (periods >= starts).fillna(False).to_numpy(dtype=bool)
    if spec.treated is not None:
        indicator = df[spec.treated]
        if indicator.isna().any() or not indicator.isin([0, 1]).all():
            findings.append(_finding("invalid_treated", True, "treated must be 0/1, non-missing"))
        else:
            bad = indicator.to_numpy(dtype=bool) != post
            if bad.any():
                findings.append(
                    _finding(
                        "treated_inconsistent_with_start",
                        True,
                        "treated indicator disagrees with period >= treatment_start",
                        df.loc[bad, u],
                    )
                )
            ordered = df.sort_values([u, p])
            switched_off = ordered.groupby(u)[spec.treated].diff() < 0
            if switched_off.any():
                findings.append(
                    _finding(
                        "non_absorbing_treatment",
                        True,
                        "treatment switches off; only absorbing (staggered adoption) "
                        "designs are supported",
                        ordered.loc[switched_off, u],
                    )
                )

    first, last = int(periods.min()), int(periods.max())
    unit_start = df.groupby(u)[s].first()
    unit_first = df.groupby(u)[p].min()
    always = unit_start.index[(unit_start <= unit_first).fillna(False).to_numpy(dtype=bool)]
    if len(always):
        findings.append(
            _finding(
                "always_treated_units",
                False,
                "units treated in their first observed period have no pre-treatment data and "
                "cannot contribute to DiD comparisons",
                always,
            )
        )
    late = unit_start.index[(unit_start > last).fillna(False).to_numpy(dtype=bool)]
    if len(late):
        findings.append(
            _finding(
                "start_after_window",
                False,
                "treatment starts after the last observed period; these units are "
                "not-yet-treated throughout the data",
                late,
            )
        )
    counts = df.groupby(u)[p].nunique()
    n_periods = periods.nunique()
    balanced = bool((counts == n_periods).all())
    if not balanced:
        findings.append(
            _finding(
                "unbalanced_panel",
                False,
                f"units observed in fewer than all {n_periods} periods",
                counts.index[counts < n_periods],
            )
        )
    if df[spec.outcome].isna().any():
        findings.append(
            _finding(
                "missing_outcome",
                False,
                f"{int(df[spec.outcome].isna().sum())} unit-periods lack an outcome",
            )
        )

    in_window = unit_start[(unit_start >= first) & (unit_start <= last)].dropna()
    timing = PanelTiming(
        periods=tuple(sorted(int(x) for x in periods.unique())),
        cohorts=dict(Counter(int(v) for v in sorted(in_window.to_numpy()))),
        n_units=int(unit_start.size),
        n_never_treated=int(unit_start.isna().sum()),
        n_always_treated=len(always),
        balanced=balanced,
    )
    result = DiagnosticResult(name=NAME, findings=tuple(findings), metrics=timing.to_json())
    return result, (None if result.is_blocking else timing)


def annotate_timing(df: pd.DataFrame, spec: PanelSpec) -> pd.DataFrame:
    """Add cohort / relative-time columns used by DiD estimators."""
    start = df[spec.treatment_start]
    period = df[spec.period]
    return df.assign(
        ever_treated=start.notna(),
        never_treated=start.isna(),
        post=(period >= start).fillna(False),
        not_yet_treated=(period < start) | start.isna(),
        rel_time=(period - start),
    )
