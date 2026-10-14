"""Task 2.3: hand-computed balance fixtures match."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.diagnostics.balance import standardized_mean_difference
from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.experiments import Arm, ExperimentSpec
from causalimpact.experiments.balance import check_baseline_balance


def cov(name: str, dtype: CovariateDType, pre: TriState = TriState.TRUE) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="pre-assignment",
        pre_treatment=pre,
        descendant_of_treatment=TriState.FALSE,
    )


SPEC = ExperimentSpec(
    experiment_id="exp",
    arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
    control_arm="control",
    randomization_unit="user_id",
    analysis_unit="user_id",
    primary_metric="y",
)

FIXTURE = pd.DataFrame(
    {
        "arm": ["treatment"] * 4 + ["control"] * 5,
        "age": [1.0, 2.0, 3.0, 4.0, 2.0, 3.0, 4.0, 5.0, 6.0],
        "is_mobile": [1, 1, 0, 0, 1, 0, 0, 0, 0],
        "region": ["eu", "eu", "us", "us", "eu", "us", "us", "us", "apac"],
    }
)
COVS = (
    cov("age", CovariateDType.NUMERIC),
    cov("is_mobile", CovariateDType.BINARY),
    cov("region", CovariateDType.CATEGORICAL),
)


def table() -> dict[tuple[str, str | None], dict[str, object]]:
    result = check_baseline_balance(SPEC, FIXTURE, COVS)
    rows = result.metrics["table"]
    assert isinstance(rows, list)
    return {(r["covariate"], r["level"]): r for r in rows}  # type: ignore[index,misc]


def test_numeric_smd_matches_hand_computation() -> None:
    row = table()[("age", None)]
    # treated mean 2.5, var 5/3; control mean 4, var 2.5
    expected = (2.5 - 4.0) / math.sqrt((5 / 3 + 2.5) / 2)
    assert row["smd"] == pytest.approx(expected)
    assert row["smd"] == pytest.approx(-1.0392305)
    assert row["mean_treated"] == pytest.approx(2.5)
    assert row["sd_control"] == pytest.approx(math.sqrt(2.5))
    assert (row["n_treated"], row["n_control"]) == (4, 5)


def test_binary_smd_uses_p_times_one_minus_p() -> None:
    row = table()[("is_mobile", None)]
    expected = (0.5 - 0.2) / math.sqrt((0.25 + 0.16) / 2)
    assert row["smd"] == pytest.approx(expected)
    assert row["smd"] == pytest.approx(0.6625891)


def test_categorical_levels_are_indicators() -> None:
    rows = table()
    # eu: treated 2/4, control 1/5
    assert rows[("region", "eu")]["smd"] == pytest.approx((0.5 - 0.2) / math.sqrt(0.205))
    # apac: treated 0/4, control 1/5
    assert rows[("region", "apac")]["smd"] == pytest.approx(-0.2 / math.sqrt(0.16 / 2))
    assert {k[1] for k in rows if k[0] == "region"} == {"apac", "eu", "us"}


def test_imbalance_is_a_warning_not_a_block() -> None:
    result = check_baseline_balance(SPEC, FIXTURE, COVS)
    assert result.status is DiagnosticStatus.WARNING
    assert result.finding("smd_above_threshold").count == 5
    assert "p_value" not in str(result.metrics)
    assert any("no balance hypothesis tests" in n for n in result.notes)


def test_missing_values_are_counted_not_imputed() -> None:
    data = FIXTURE.assign(age=FIXTURE["age"].where(FIXTURE.index != 0))
    row = {
        (r["covariate"], r["level"]): r
        for r in check_baseline_balance(SPEC, data, COVS).metrics["table"]  # type: ignore[union-attr]
    }[("age", None)]
    assert (row["missing_treated"], row["n_treated"]) == (1, 3)
    assert row["mean_treated"] == pytest.approx(3.0)


def test_post_treatment_covariate_refused() -> None:
    with pytest.raises(ValueError, match="not eligible"):
        check_baseline_balance(SPEC, FIXTURE, (cov("age", CovariateDType.NUMERIC, TriState.FALSE),))


def test_smd_edge_cases() -> None:
    same = np.array([3.0, 3.0])
    assert standardized_mean_difference(same, same) == 0.0
    assert standardized_mean_difference(same, np.array([4.0, 4.0])) is None
    assert standardized_mean_difference(np.array([]), same) is None


def test_multi_arm_compares_each_arm_to_control() -> None:
    spec = SPEC.model_copy(
        update={
            "arms": (
                Arm(name="control", allocation=0.5),
                Arm(name="a", allocation=0.25),
                Arm(name="b", allocation=0.25),
            )
        }
    )
    data = pd.DataFrame({"arm": ["control", "a", "b"] * 4, "age": np.arange(12.0)})
    rows = check_baseline_balance(spec, data, (COVS[0],)).metrics["table"]
    assert [r["comparison"] for r in rows] == ["a vs control", "b vs control"]  # type: ignore[index,union-attr]


@pytest.mark.simulation
def test_randomized_balance_is_small_on_large_samples(rng: np.random.Generator) -> None:
    n = 20_000
    data = pd.DataFrame(
        {
            "arm": rng.permutation(np.repeat(["control", "treatment"], n // 2)),
            "age": rng.normal(40, 10, n),
            "is_mobile": rng.integers(0, 2, n),
            "region": rng.choice(["eu", "us", "apac"], n),
        }
    )
    result = check_baseline_balance(SPEC, data, COVS)
    assert result.status is DiagnosticStatus.PASS
    assert result.metrics["max_abs_smd"] < 0.05  # type: ignore[operator]
