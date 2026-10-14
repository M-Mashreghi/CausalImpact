"""Task 3.4: toy match pairs are reproducible; diagnostics report balance and drops."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.observational.matching import (
    MatchingConfig,
    match_on_propensity,
    matched_sample_diagnostics,
)
from causalimpact.observational.propensity import PropensityScores, estimate_propensity
from tests.unit.observational.test_propensity import TREATMENT, confounded

TOY = PropensityScores(
    unit_ids=np.array(["t1", "t2", "t3", "c1", "c2", "c3", "c4"]),
    treated=np.array([1, 1, 1, 0, 0, 0, 0], dtype=float),
    scores=np.array([0.30, 0.60, 0.95, 0.29, 0.50, 0.62, 0.10]),
)


def test_toy_pairs_without_caliper() -> None:
    match = match_on_propensity(TOY, MatchingConfig(caliper_sd=None))
    pairs = dict(zip(match.pairs["treated_id"], match.pairs["control_id"], strict=True))
    assert pairs == {"t1": "c1", "t2": "c3", "t3": "c3"}
    # c3 is reused (with replacement); weights reflect usage.
    assert match.unit_weights["c3"] == 2.0
    assert match.unit_weights["c2"] == 0.0
    assert match.unit_weights["t1"] == 1.0


def test_caliper_drops_unmatchable_treated_unit() -> None:
    match = match_on_propensity(TOY, MatchingConfig(caliper_sd=0.2))
    assert match.unmatched_treated.tolist() == ["t3"]
    assert set(match.pairs["treated_id"]) == {"t1", "t2"}


def test_one_to_two_matching() -> None:
    match = match_on_propensity(TOY, MatchingConfig(k=2, caliper_sd=None))
    t1 = match.pairs.loc[match.pairs["treated_id"] == "t1", "control_id"].tolist()
    assert t1 == ["c1", "c2"]
    assert match.unit_weights.loc[["c1", "c2", "c3", "c4"]].sum() == pytest.approx(3.0)


def test_matching_is_order_independent() -> None:
    perm = np.array([6, 2, 4, 0, 5, 1, 3])
    shuffled = PropensityScores(TOY.unit_ids[perm], TOY.treated[perm], TOY.scores[perm])
    a = match_on_propensity(TOY, MatchingConfig(caliper_sd=None)).pairs
    b = match_on_propensity(shuffled, MatchingConfig(caliper_sd=None)).pairs
    key = ["treated_id", "control_id"]
    pd.testing.assert_frame_equal(
        a.sort_values(key).reset_index(drop=True), b.sort_values(key).reset_index(drop=True)
    )


def test_without_replacement_refused() -> None:
    with pytest.raises(ValueError, match="with replacement"):
        match_on_propensity(TOY, MatchingConfig(replace=False))


COVS = (
    CovariateSpec(
        name="x1",
        dtype=CovariateDType.NUMERIC,
        measurement_time="baseline",
        pre_treatment=TriState.TRUE,
        descendant_of_treatment=TriState.FALSE,
    ),
    CovariateSpec(
        name="region",
        dtype=CovariateDType.CATEGORICAL,
        measurement_time="baseline",
        pre_treatment=TriState.TRUE,
        descendant_of_treatment=TriState.FALSE,
    ),
)


def test_matching_improves_balance_on_confounded_data(rng: np.random.Generator) -> None:
    data = confounded(rng, n=4000)
    ps = estimate_propensity(data, TREATMENT, COVS)
    match = match_on_propensity(ps)
    result = matched_sample_diagnostics(match, data, ps.treated, COVS)
    before, after = result.metrics["max_abs_smd_before"], result.metrics["max_abs_smd_after"]
    assert before > 0.3  # type: ignore[operator]
    assert after < 0.1  # type: ignore[operator]
    assert result.metrics["n_matched_treated"] + result.metrics["n_unmatched_treated"] == int(  # type: ignore[operator]
        ps.treated.sum()
    )
    assert result.metrics["mean_distance"] <= result.metrics["caliper_logit"]  # type: ignore[operator]


def test_dropped_treated_units_change_reported_target_population() -> None:
    data = pd.DataFrame(
        {
            "unit_id": TOY.unit_ids,
            "x1": [1.0, 2.0, 3.0, 1.1, 1.5, 2.1, 0.5],
            "region": ["a", "b", "b", "a", "b", "b", "a"],
        }
    )
    match = match_on_propensity(TOY, MatchingConfig(caliper_sd=0.2))
    result = matched_sample_diagnostics(match, data, TOY.treated, COVS)
    assert "treated_units_dropped" in result.codes()
    assert result.metrics["target_population"] == "matched treated units"
    assert "ATT among matched treated units" in result.finding("treated_units_dropped").message
