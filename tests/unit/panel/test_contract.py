"""Task 4.1: malformed timing fixtures fail; valid panels are summarised."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.panel.contract import PanelSpec, annotate_timing, validate_panel

SPEC = PanelSpec(treated="treated")


def panel(
    starts: dict[str, float | None], periods: range = range(1, 7), **extra: Any
) -> pd.DataFrame:
    rows = []
    for unit, start in starts.items():
        for t in periods:
            treated = int(start is not None and t >= start)
            rows.append(
                {
                    "unit_id": unit,
                    "period": t,
                    "treatment_start": np.nan if start is None else start,
                    "treated": treated,
                    "outcome": float(t + treated),
                }
            )
    return pd.DataFrame(rows).assign(**extra)


STAGGERED = {"a": 3, "b": 3, "c": 5, "d": None, "e": None}


def test_valid_staggered_panel() -> None:
    result, timing = validate_panel(panel(STAGGERED), SPEC)
    assert result.status is DiagnosticStatus.PASS, result.findings
    assert timing is not None
    assert timing.cohorts == {3: 2, 5: 1}
    assert timing.n_never_treated == 2
    assert timing.is_staggered and timing.balanced
    assert timing.periods == (1, 2, 3, 4, 5, 6)


def test_annotation_columns() -> None:
    df = annotate_timing(panel(STAGGERED), SPEC)
    row = df[(df.unit_id == "c") & (df.period == 4)].iloc[0]
    assert (row.rel_time, row.post, row.not_yet_treated) == (-1, False, True)
    never = df[df.unit_id == "d"]
    assert never["never_treated"].all() and never["rel_time"].isna().all()


def _dup(df: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([df, df.iloc[[0]]])


def _varying_start(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[(df.unit_id == "a") & (df.period == 6), "treatment_start"] = 4
    return df


def _flip_indicator(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[(df.unit_id == "a") & (df.period == 2), "treated"] = 1
    return df


def _switch_off(df: pd.DataFrame) -> pd.DataFrame:
    df.loc[(df.unit_id == "a") & (df.period == 5), "treated"] = 0
    return df


@pytest.mark.parametrize(
    ("corrupt", "code"),
    [
        (_dup, "duplicate_unit_period"),
        (_varying_start, "inconsistent_start"),
        (_flip_indicator, "treated_inconsistent_with_start"),
        (_switch_off, "non_absorbing_treatment"),
        (lambda d: d.assign(period=d.period + 0.5), "non_integer_period"),
        (lambda d: d.assign(treatment_start=d.treatment_start + 0.5), "non_integer_start"),
        (lambda d: d.assign(treated=2), "invalid_treated"),
        (lambda d: d.drop(columns="treatment_start"), "missing_column"),
        (lambda d: d.assign(period=d.period.where(d.index != 0)), "missing_unit_or_period"),
    ],
)
def test_malformed_timing_blocks(corrupt: Any, code: str) -> None:
    result, timing = validate_panel(corrupt(panel(STAGGERED)), SPEC)
    assert result.is_blocking
    assert code in result.codes()
    assert timing is None


@pytest.mark.parametrize(
    ("starts", "code"),
    [
        ({"a": 1, "b": None}, "always_treated_units"),
        ({"a": 9, "b": None}, "start_after_window"),
    ],
)
def test_restrictive_timing_warns(starts: dict[str, float | None], code: str) -> None:
    result, timing = validate_panel(panel(starts), SPEC)
    assert result.status is DiagnosticStatus.WARNING
    assert code in result.codes()
    assert timing is not None


def test_unbalanced_panel_and_missing_outcome_warn() -> None:
    df = panel(STAGGERED)
    df = df.drop(df.index[(df.unit_id == "e") & (df.period == 6)])
    df.loc[0, "outcome"] = np.nan
    result, timing = validate_panel(df, SPEC)
    assert {"unbalanced_panel", "missing_outcome"} <= result.codes()
    assert timing is not None and not timing.balanced


def test_treated_indicator_is_optional() -> None:
    result, _ = validate_panel(panel(STAGGERED).drop(columns="treated"), PanelSpec())
    assert result.status is DiagnosticStatus.PASS
