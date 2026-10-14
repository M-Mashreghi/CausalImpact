"""Task 2.10: differential attrition triggers a block; decisions respect it."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.experiments import Arm, ExperimentSpec
from causalimpact.experiments.attrition import check_attrition
from causalimpact.experiments.decision import DecisionLabel, decide
from tests.unit.experiments.test_decision import ANALYSED, POLICY, results
from tests.unit.experiments.test_decision import SPEC as DECISION_SPEC

SPEC = ExperimentSpec(
    experiment_id="exp",
    arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
    control_arm="control",
    randomization_unit="user_id",
    analysis_unit="user_id",
    primary_metric="y",
)


def make(
    rng: np.random.Generator, n: int, miss_control: float, miss_treated: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    users = [f"u{i}" for i in range(n)]
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    day = rng.choice(["d1", "d2", "d3"], n)
    assignments = pd.DataFrame({"user_id": users, "arm": arm, "day": day})
    rate = np.where(arm == "treatment", miss_treated, miss_control)
    y = rng.normal(size=n)
    y[rng.random(n) < rate] = np.nan
    analysis = pd.DataFrame({"user_id": users, "arm": arm, "y": y})
    return assignments, analysis


def test_balanced_attrition_passes(rng: np.random.Generator) -> None:
    a, d = make(rng, 20_000, 0.05, 0.05)
    result = check_attrition(SPEC, a, d, "y", period_column="day")
    assert result.status is DiagnosticStatus.PASS, result.findings
    assert result.metrics["overall_attrition_rate"] == pytest.approx(0.05, abs=0.01)
    assert len(result.metrics["by_period"]) == 3  # type: ignore[arg-type]


def test_differential_attrition_blocks(rng: np.random.Generator) -> None:
    a, d = make(rng, 20_000, 0.05, 0.10)
    result = check_attrition(SPEC, a, d, "y")
    assert result.is_blocking
    assert "differential_attrition" in result.codes()
    by_arm = result.metrics["by_arm"]
    assert by_arm["treatment"]["attrition_rate"] > by_arm["control"]["attrition_rate"]  # type: ignore[index,call-overload]


def test_large_difference_blocks_even_when_underpowered(rng: np.random.Generator) -> None:
    a, d = make(rng, 60, 0.0, 0.1)
    result = check_attrition(SPEC, a, d, "y", max_rate_difference=0.02)
    assert result.is_blocking


def test_units_missing_from_analysis_count_as_attrited(rng: np.random.Generator) -> None:
    a, d = make(rng, 2000, 0.0, 0.0)
    treated_rows = d.index[d["arm"] == "treatment"][:200]
    result = check_attrition(SPEC, a, d.drop(index=treated_rows), "y")
    assert result.metrics["by_arm"]["treatment"]["n_attrited"] == 200  # type: ignore[index,call-overload]
    assert result.is_blocking


def test_resolution_downgrades_but_keeps_finding(rng: np.random.Generator) -> None:
    a, d = make(rng, 20_000, 0.05, 0.10)
    result = check_attrition(SPEC, a, d, "y", resolution="Lee bounds reported; sign robust")
    assert result.status is DiagnosticStatus.WARNING
    assert "Lee bounds" in result.finding("differential_attrition_resolved").message


def test_high_overall_attrition_warns(rng: np.random.Generator) -> None:
    a, d = make(rng, 20_000, 0.3, 0.3)
    assert "high_overall_attrition" in check_attrition(SPEC, a, d, "y").codes()


def test_period_level_differential_is_reported(rng: np.random.Generator) -> None:
    a, d = make(rng, 30_000, 0.05, 0.05)
    in_d3 = (a["day"] == "d3") & (a["arm"] == "treatment")
    d.loc[in_d3.to_numpy(), "y"] = np.nan
    result = check_attrition(SPEC, a, d, "y", period_column="day")
    assert result.finding("differential_attrition_period").examples == ("d3",)


def test_blocking_attrition_blocks_the_decision_label(rng: np.random.Generator) -> None:
    a, d = make(rng, 20_000, 0.05, 0.10)
    attrition = check_attrition(SPEC, a, d, "y")
    decision = decide(DECISION_SPEC, POLICY, results(), [attrition], analysed_at=ANALYSED)
    assert decision.label is DecisionLabel.BLOCKED
    assert "attrition" in decision.reasons[0]


def test_missing_columns_rejected(rng: np.random.Generator) -> None:
    a, d = make(rng, 100, 0.0, 0.0)
    with pytest.raises(ValueError, match="missing columns"):
        check_attrition(SPEC, a, d.drop(columns="y"), "y")
