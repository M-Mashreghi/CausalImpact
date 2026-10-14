"""Task 7.4: severe overlap triggers a block/warning before silent extrapolation."""

from __future__ import annotations

import pytest

from causalimpact.domain import EstimandType
from causalimpact.estimators import Estimator
from causalimpact.observational.overlap import OverlapPolicy
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme
from causalimpact.simulation.stress import overlap_sweep
from tests.unit.observational.test_weighting import TREATMENT, X, estimand

pytestmark = pytest.mark.simulation
ATE = estimand(EstimandType.ATE)
STRENGTHS = (0.5, 2.0, 4.0, 7.0)


def guarded_ipw(seed: int) -> Estimator:
    return WeightingEstimator(TREATMENT, (X,), WeightScheme.IPW, seed=seed, n_bootstrap=50)


def unguarded_ipw(seed: int) -> Estimator:
    """IPW with refusal disabled, to expose what the guard prevents."""
    permissive = OverlapPolicy(block_violation_fraction=1.0, block_ess_fraction=1e-9)
    return WeightingEstimator(
        TREATMENT, (X,), WeightScheme.IPW, seed=seed, n_bootstrap=50, overlap_policy=permissive
    )


def test_guarded_ipw_refuses_under_severe_overlap() -> None:
    points = overlap_sweep(STRENGTHS, guarded_ipw, ATE, TREATMENT, (X,), n_replicates=12, seed=1)
    mild, severe = points[0], points[-1]
    assert mild.overlap_status.get("pass", 0) == mild.n_replicates
    assert mild.n_refused == 0
    assert severe.overlap_status.get("blocking", 0) >= 0.9 * severe.n_replicates
    assert severe.refusal_rate >= 0.9
    rates = [p.refusal_rate for p in points]
    assert rates == sorted(rates)


def test_no_catastrophic_error_passes_silently() -> None:
    points = overlap_sweep(STRENGTHS, unguarded_ipw, ATE, TREATMENT, (X,), n_replicates=12, seed=2)
    assert sum(p.n_catastrophic for p in points) > 0  # unguarded IPW does break down
    assert all(p.n_catastrophic_unflagged == 0 for p in points)
    assert points[-1].rmse is not None and points[0].rmse is not None
    assert points[-1].rmse > 3 * points[0].rmse  # instability grows with poor overlap
