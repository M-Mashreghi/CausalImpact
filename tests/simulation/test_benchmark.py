"""Task 7.2: a simple unbiased estimator benchmark passes tolerance."""

from __future__ import annotations

import pytest

from causalimpact.domain import (
    Estimand,
    EstimandType,
    TargetPopulation,
    TreatmentBasis,
    TreatmentSpec,
)
from causalimpact.estimators import Estimator
from causalimpact.experiments.estimators import DifferenceInMeans
from causalimpact.simulation.benchmark import (
    BenchmarkCase,
    bias_within_tolerance,
    run_benchmark,
)
from causalimpact.simulation.dgp import ObservationalConfig, RCTConfig

pytestmark = pytest.mark.simulation

POP = TargetPopulation(name="sim", description="simulated units")
ITT = Estimand(
    estimand_id="itt_y",
    type=EstimandType.ITT,
    treatment="arm",
    outcome="y",
    target_population=POP,
    treatment_basis=TreatmentBasis.ASSIGNMENT,
)
ARM = TreatmentSpec(name="arm", control_value="control", treated_value="treatment")


def dim(_: int) -> Estimator:
    return DifferenceInMeans(ARM)


def test_difference_in_means_is_unbiased() -> None:
    case = BenchmarkCase("rct_dim", RCTConfig(n=1000, effect=0.5), dim, ITT, "ITT")
    result = run_benchmark(case, n_replicates=200, seed=1)
    assert result.n_succeeded == 200 and result.failures == {}
    assert bias_within_tolerance(result, abs_tol=0.01)
    assert result.rmse == pytest.approx(result.empirical_sd, rel=0.1)
    assert result.mean_std_error == pytest.approx(result.empirical_sd, rel=0.15)


def test_benchmark_is_seed_reproducible() -> None:
    case = BenchmarkCase("rct_dim", RCTConfig(n=200), dim, ITT, "ITT")
    assert run_benchmark(case, n_replicates=10, seed=3) == run_benchmark(
        case, n_replicates=10, seed=3
    )


def test_failures_are_counted_not_dropped() -> None:
    case = BenchmarkCase("rct_attrition", RCTConfig(n=200, attrition_treated=0.3), dim, ITT, "ITT")
    result = run_benchmark(case, n_replicates=5, seed=1)
    assert result.failures == {"ValueError": 5}  # missing outcomes are refused
    assert result.failure_rate == 1.0 and result.bias is None
    assert not bias_within_tolerance(result, abs_tol=1.0)


def test_confounded_naive_contrast_fails_tolerance() -> None:
    """A biased estimator must not pass: naive contrast on confounded data."""
    naive_itt = ITT.model_copy(update={"treatment": "treated", "outcome": "y"})

    def naive(_: int) -> Estimator:
        return DifferenceInMeans(TreatmentSpec(name="treated"))

    case = BenchmarkCase("confounded_naive", ObservationalConfig(n=1000), naive, naive_itt, "ATE")
    result = run_benchmark(case, n_replicates=30, seed=2)
    assert result.bias is not None and result.bias > 2.0
    assert not bias_within_tolerance(result, abs_tol=0.1)
