"""Monte Carlo benchmark harness: estimator x DGP (Task 7.2).

For each replicate a fresh dataset is simulated with a seed derived from the benchmark
seed, the estimator is run, and the estimate is compared with that replicate's true
estimand. Failures (any exception) are counted by type, never dropped. Reported: bias
with its Monte Carlo standard error, RMSE, empirical SD of the estimates, mean reported
SE, and the failure rate.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from pydantic import BaseModel, ConfigDict

from causalimpact.domain.estimands import EffectEstimate, Estimand
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.simulation.dgp import SimulationConfig, simulate

EstimatorFactory = Callable[[int], Estimator]
"""Builds the estimator for one replicate from a replicate-specific seed."""


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    config: SimulationConfig
    estimator: EstimatorFactory
    estimand: Estimand
    truth_key: str


class BenchmarkResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case: str
    estimator: str
    truth_key: str
    n_replicates: int
    n_succeeded: int
    failures: dict[str, int]
    bias: float | None
    bias_mc_se: float | None
    rmse: float | None
    empirical_sd: float | None
    mean_std_error: float | None
    estimates: tuple[float, ...]
    truths: tuple[float, ...]
    std_errors: tuple[float, ...]
    ci_lower: tuple[float, ...]
    ci_upper: tuple[float, ...]

    @property
    def failure_rate(self) -> float:
        return 1.0 - self.n_succeeded / self.n_replicates


def run_benchmark(
    case: BenchmarkCase, *, n_replicates: int, seed: int, confidence_level: float = 0.95
) -> BenchmarkResult:
    if n_replicates < 2:
        raise ValueError("need at least two replicates")
    outcomes: list[tuple[EffectEstimate, float]] = []
    failures: Counter[str] = Counter()
    name = ""
    for rep in range(n_replicates):
        rep_seed = derive_seed(seed, f"{case.name}:replicate:{rep}")
        dataset = simulate(case.config, rep_seed)
        estimator = case.estimator(rep_seed)
        name = estimator.name
        try:
            est = run_estimator(
                estimator, dataset.data, case.estimand, confidence_level=confidence_level
            )
        except Exception as exc:  # counted, never dropped
            failures[type(exc).__name__] += 1
            continue
        outcomes.append((est, dataset.truth[case.truth_key]))

    if not outcomes:
        empty: tuple[float, ...] = ()
        return BenchmarkResult(
            case=case.name, estimator=name, truth_key=case.truth_key, n_replicates=n_replicates,
            n_succeeded=0, failures=dict(failures), bias=None, bias_mc_se=None, rmse=None,
            empirical_sd=None, mean_std_error=None, estimates=empty, truths=empty,
            std_errors=empty, ci_lower=empty, ci_upper=empty,
        )  # fmt: skip
    estimates = np.array([e.estimate for e, _ in outcomes])
    truths = np.array([t for _, t in outcomes])
    errors = estimates - truths
    k = len(outcomes)
    return BenchmarkResult(
        case=case.name,
        estimator=name,
        truth_key=case.truth_key,
        n_replicates=n_replicates,
        n_succeeded=k,
        failures=dict(failures),
        bias=float(errors.mean()),
        bias_mc_se=float(errors.std(ddof=1) / math.sqrt(k)) if k > 1 else None,
        rmse=float(math.sqrt(np.mean(errors**2))),
        empirical_sd=float(estimates.std(ddof=1)) if k > 1 else None,
        mean_std_error=float(np.mean([e.std_error for e, _ in outcomes])),
        estimates=tuple(float(x) for x in estimates),
        truths=tuple(float(x) for x in truths),
        std_errors=tuple(e.std_error for e, _ in outcomes),
        ci_lower=tuple(e.ci_lower for e, _ in outcomes),
        ci_upper=tuple(e.ci_upper for e, _ in outcomes),
    )


def bias_within_tolerance(result: BenchmarkResult, *, abs_tol: float, z: float = 4.0) -> bool:
    """Bias is acceptable if within ``abs_tol`` plus ``z`` Monte Carlo standard errors."""
    if result.bias is None or result.bias_mc_se is None:
        return False
    return abs(result.bias) <= abs_tol + z * result.bias_mc_se
