"""Task 3.9: hand-computed weighted SMD fixtures match; Love-plot data is complete."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.diagnostics.balance import (
    balance_comparison,
    weighted_balance_rows,
    weighted_variance_ratio,
)
from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.observational.matching import match_on_propensity
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.observational.weighting import WeightScheme, compute_weights
from tests.unit.observational.test_propensity import TREATMENT, confounded


def cov(name: str, dtype: CovariateDType = CovariateDType.NUMERIC) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="baseline",
        pre_treatment=TriState.TRUE,
        descendant_of_treatment=TriState.FALSE,
    )


FIXTURE = pd.DataFrame({"x": [1.0, 3.0, 2.0, 4.0, 6.0], "b": [1, 0, 1, 0, 0]})
TREATED = np.array([True, True, False, False, False])
WEIGHTS = np.array([1.0, 3.0, 1.0, 1.0, 2.0])


def test_weighted_smd_matches_hand_computation() -> None:
    row = weighted_balance_rows(FIXTURE, TREATED, WEIGHTS, (cov("x"),), "w")[0]
    # weighted means 2.5 and 4.5; unweighted variances 2 and 4 -> pooled sd sqrt(3)
    assert row.mean_treated == pytest.approx(2.5)
    assert row.mean_control == pytest.approx(4.5)
    assert row.smd == pytest.approx(-2.0 / math.sqrt(3.0))
    assert row.smd == pytest.approx(-1.1547005)


def test_weighted_binary_smd_matches_hand_computation() -> None:
    row = weighted_balance_rows(FIXTURE, TREATED, WEIGHTS, (cov("b", CovariateDType.BINARY),), "w")[
        0
    ]
    # weighted p_t = 1/4, p_c = 1/4; unweighted p_t = 0.5, p_c = 1/3
    assert row.smd == pytest.approx(0.0)
    unweighted = weighted_balance_rows(
        FIXTURE, TREATED, np.ones(5), (cov("b", CovariateDType.BINARY),), "u"
    )[0]
    expected = (0.5 - 1 / 3) / math.sqrt((0.25 + (1 / 3) * (2 / 3)) / 2)
    assert unweighted.smd == pytest.approx(expected)


def test_weighted_variance_ratio_hand_computed() -> None:
    ratio = weighted_variance_ratio(FIXTURE["x"].to_numpy(), TREATED, WEIGHTS)
    assert ratio == pytest.approx(0.75 / 2.75)


def test_unit_weights_reproduce_unweighted_smd() -> None:
    from causalimpact.diagnostics.balance import standardized_mean_difference

    row = weighted_balance_rows(FIXTURE, TREATED, np.ones(5), (cov("x"),), "u")[0]
    x = FIXTURE["x"].to_numpy()
    assert row.smd == pytest.approx(standardized_mean_difference(x[TREATED], x[~TREATED]))


def test_invalid_weights_rejected() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        weighted_balance_rows(FIXTURE, TREATED, -WEIGHTS, (cov("x"),), "w")


def test_love_plot_before_and_after_adjustments(rng: np.random.Generator) -> None:
    data = confounded(rng, n=4000)
    covs = (cov("x1"), cov("x2"), cov("region", CovariateDType.CATEGORICAL))
    ps = estimate_propensity(data, TREATMENT, covs)
    ipw = compute_weights(WeightScheme.IPW, ps.scores, ps.treated)
    matched = match_on_propensity(ps).unit_weights.reindex(data["unit_id"]).to_numpy()
    result = balance_comparison(
        data, ps.treated.astype(bool), covs, {"ipw": ipw, "matched": matched}
    )
    summary = result.metrics["summary"]
    assert summary["unadjusted"]["max_abs_smd"] > 0.3  # type: ignore[index,call-overload,operator]
    assert summary["ipw"]["max_abs_smd"] < 0.1  # type: ignore[index,call-overload,operator]
    assert summary["matched"]["max_abs_smd"] < 0.1  # type: ignore[index,call-overload,operator]
    love = result.metrics["love_plot"]
    # 2 numeric + 2 region levels, for each of 3 adjustments
    assert len(love) == 12  # type: ignore[arg-type]
    assert {p["adjustment"] for p in love} == {"unadjusted", "ipw", "matched"}  # type: ignore[index,union-attr]
    assert result.status is DiagnosticStatus.PASS


def test_residual_imbalance_is_flagged() -> None:
    result = balance_comparison(FIXTURE, TREATED, (cov("x"),), {"bad": WEIGHTS})
    assert "residual_imbalance" in result.codes()
    assert "variance_ratio_out_of_bounds" in result.codes()


def test_unadjusted_label_reserved() -> None:
    with pytest.raises(ValueError, match="reserved"):
        balance_comparison(FIXTURE, TREATED, (cov("x"),), {"unadjusted": WEIGHTS})
