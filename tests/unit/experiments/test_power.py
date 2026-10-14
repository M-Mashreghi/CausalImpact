"""Task 2.7: power / MDE / sample-size reference examples match tolerance."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from causalimpact.estimators import run_estimator
from causalimpact.experiments.power import (
    MetricType,
    PowerInputs,
    minimum_detectable_effect,
    power,
    sample_size,
)
from tests.unit.experiments.test_estimators import DIM, DIP, ITT

CONT = PowerInputs(metric_type=MetricType.CONTINUOUS, std_dev=1.0)
BIN = PowerInputs(metric_type=MetricType.BINARY, baseline_rate=0.10)


class TestReferenceExamples:
    def test_cohen_d_half(self) -> None:
        # Classic normal-approximation result: 2 (1.96 + 0.8416)^2 / 0.25 = 62.8 -> 63 per arm.
        plan = sample_size(CONT, 0.5)
        assert (plan.n_treated, plan.n_control) == (63, 63)

    def test_binary_ten_to_twelve_percent(self) -> None:
        # Unpooled normal approximation:
        # (z_a + z_b)^2 (0.12*0.88 + 0.1*0.9) / 0.02^2 = 3838.4 -> 3839 per arm.
        plan = sample_size(BIN, 0.02)
        expected = (1.959964 + 0.841621) ** 2 * (0.12 * 0.88 + 0.10 * 0.90) / 0.02**2
        assert plan.n_treated == math.ceil(expected) == 3839
        assert plan.n_control == plan.n_treated

    def test_power_at_planned_size_is_target(self) -> None:
        plan = sample_size(CONT, 0.5)
        assert power(CONT, 0.5, plan.n_total) == pytest.approx(0.8, abs=0.005)

    def test_size_of_test_is_alpha(self) -> None:
        assert power(CONT, 0.0, 1000) == pytest.approx(0.05)


class TestConsistency:
    @pytest.mark.parametrize("inputs", [CONT, BIN], ids=["continuous", "binary"])
    @pytest.mark.parametrize("n_total", [500, 5000, 50_000])
    def test_mde_and_sample_size_are_inverse(self, inputs: PowerInputs, n_total: int) -> None:
        mde = minimum_detectable_effect(inputs, n_total)
        assert sample_size(inputs, mde).n_total == pytest.approx(n_total, abs=2)

    def test_unequal_allocation_needs_more_units(self) -> None:
        skewed = CONT.model_copy(update={"treated_fraction": 0.2})
        plan = sample_size(skewed, 0.5)
        assert plan.n_total > sample_size(CONT, 0.5).n_total
        assert plan.n_treated / plan.n_total == pytest.approx(0.2, abs=0.01)
        # 1/a + 1/(1-a) = 6.25 vs 4 for equal allocation.
        assert plan.n_total / sample_size(CONT, 0.5).n_total == pytest.approx(6.25 / 4, rel=0.02)

    def test_variance_reduction_shrinks_requirements(self) -> None:
        cuped = CONT.model_copy(update={"variance_reduction": 0.5})
        assert sample_size(cuped, 0.5).n_total == pytest.approx(
            sample_size(CONT, 0.5).n_total / 2, abs=2
        )

    def test_power_increases_with_n_and_effect(self) -> None:
        assert power(CONT, 0.2, 1000) < power(CONT, 0.2, 4000) < power(CONT, 0.4, 4000)


class TestValidation:
    def test_continuous_needs_std_dev(self) -> None:
        with pytest.raises(ValidationError, match="std_dev"):
            PowerInputs(metric_type=MetricType.CONTINUOUS)

    def test_binary_needs_baseline(self) -> None:
        with pytest.raises(ValidationError, match="baseline_rate"):
            PowerInputs(metric_type=MetricType.BINARY, std_dev=1.0)

    def test_invalid_proportion_effect(self) -> None:
        with pytest.raises(ValueError, match="valid proportion"):
            sample_size(BIN, 0.95)

    def test_zero_effect_cannot_be_planned(self) -> None:
        with pytest.raises(ValueError, match="zero effect"):
            sample_size(CONT, 0.0)


@pytest.mark.simulation
@pytest.mark.parametrize(
    ("inputs", "effect", "estimator", "binary"),
    [(CONT, 0.25, DIM, False), (BIN, 0.03, DIP, True)],
    ids=["continuous", "binary"],
)
def test_planned_power_is_achieved_by_the_estimator(
    rng: np.random.Generator, inputs: PowerInputs, effect: float, estimator: object, binary: bool
) -> None:
    plan = sample_size(inputs, effect)
    n = plan.n_total + plan.n_total % 2
    sims, rejections = 600, 0
    for _ in range(sims):
        arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
        treated = arm == "treatment"
        if binary:
            y = rng.binomial(1, np.where(treated, 0.10 + effect, 0.10)).astype(float)
        else:
            y = rng.normal(0.0, 1.0, n) + effect * treated
        out = run_estimator(estimator, pd.DataFrame({"arm": arm, "y": y}), ITT)  # type: ignore[arg-type]
        rejections += out.ci_lower > 0 or out.ci_upper < 0
    # Target 0.80; Monte Carlo SE ~0.016 at 600 simulations.
    assert 0.75 <= rejections / sims <= 0.85
