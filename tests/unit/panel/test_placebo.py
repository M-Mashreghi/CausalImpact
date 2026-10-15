"""Task 4.10: null / treated fixtures produce the expected placebo rank behaviour."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.panel.placebo import (
    did_in_time_placebo,
    in_space_placebo_test,
    in_time_placebo_test,
)
from causalimpact.simulation.dgp import PanelConfig, simulate
from tests.unit.panel.test_did import ATT
from tests.unit.panel.test_synthetic_control import panel


def test_treated_unit_ranks_first_with_a_real_effect(rng: np.random.Generator) -> None:
    result = in_space_placebo_test(panel(rng, effect=5.0, own_sd=0.0, noise=0.1))
    assert result.metrics["rank"] == 1
    assert result.metrics["p_value"] == pytest.approx(1 / 21)
    assert result.codes() == set()
    assert len(result.metrics["placebos"]) == 20  # type: ignore[arg-type]
    assert "does not prove" in result.notes[0]


def test_null_effect_is_not_extreme_most_of_the_time(rng: np.random.Generator) -> None:
    flagged = [
        "effect_not_extreme_among_placebos"
        in in_space_placebo_test(panel(rng, effect=0.0, noise=0.3)).codes()
        for _ in range(10)
    ]
    assert np.mean(flagged) >= 0.7


def test_rank_p_value_is_roughly_uniform_under_the_null(rng: np.random.Generator) -> None:
    ps = [
        in_space_placebo_test(panel(rng, effect=0.0, noise=0.3)).metrics["p_value"]
        for _ in range(30)
    ]
    assert 0.3 < np.mean(ps) < 0.7  # type: ignore[arg-type]


def test_small_donor_pool_cannot_be_significant(rng: np.random.Generator) -> None:
    result = in_space_placebo_test(panel(rng, n_donors=6, effect=5.0, own_sd=0.0))
    assert "insufficient_placebos" in result.codes()
    assert result.metrics["minimum_attainable_p_value"] == pytest.approx(1 / 7)


def test_in_time_placebo_is_quiet_without_a_pre_period_shock(rng: np.random.Generator) -> None:
    result = in_time_placebo_test(panel(rng, effect=5.0, own_sd=0.0, noise=0.1), fake_period=9)
    assert result.codes() == set()
    assert abs(result.metrics["placebo_att"]) < 0.5  # type: ignore[arg-type]


def test_in_time_placebo_flags_a_pre_period_break(rng: np.random.Generator) -> None:
    data = panel(rng, effect=2.0, own_sd=0.0, noise=0.1)
    shifted = (data.unit_id == "treated") & (data.period >= 9)
    data.loc[shifted, "outcome"] += 2.0  # the "effect" starts before the real date
    result = in_time_placebo_test(data, fake_period=9)
    assert "in_time_placebo_effect" in result.codes()


def test_fake_period_must_be_in_pre_window(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="pre-treatment window"):
        in_time_placebo_test(panel(rng), fake_period=16)


@pytest.mark.parametrize(("slope", "flagged"), [(0.0, False), (0.6, True)])
def test_did_in_time_placebo(slope: float, flagged: bool) -> None:
    data = simulate(PanelConfig(n_units=400, n_periods=8, pre_trend_slope=slope), seed=3).data
    result = did_in_time_placebo(data, ATT, fake_period=3)
    assert ("in_time_placebo_effect" in result.codes()) is flagged
