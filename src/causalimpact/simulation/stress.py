"""Poor-overlap and extreme-weight stress tests (Task 7.4).

Sweeps confounding strength (which degrades overlap) on the observational DGP. For every
replicate it records the overlap diagnostic status, whether the estimator refused, its
error against the truth, and whether the error was catastrophic. The key safety
property: a catastrophic error must never occur on a replicate whose overlap diagnostic
passed silently (``n_catastrophic_unflagged`` must be zero).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

from causalimpact.domain.estimands import Estimand
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.observational.overlap import (
    OverlapPolicy,
    OverlapRefusedError,
    check_overlap,
)
from causalimpact.observational.propensity import ConvergenceError, estimate_propensity
from causalimpact.simulation.dgp import ObservationalConfig, simulate


class StressPoint(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    confounding_strength: float
    n_replicates: int
    overlap_status: dict[str, int]
    n_refused: int
    n_failed: int
    bias: float | None
    rmse: float | None
    max_abs_error: float | None
    n_catastrophic: int
    n_catastrophic_unflagged: int

    @property
    def refusal_rate(self) -> float:
        return self.n_refused / self.n_replicates


def overlap_sweep(
    strengths: Sequence[float],
    estimator: Callable[[int], Estimator],
    estimand: Estimand,
    treatment: TreatmentSpec,
    covariates: tuple[CovariateSpec, ...],
    *,
    n: int = 1500,
    n_replicates: int = 20,
    seed: int = 0,
    catastrophic_error: float = 1.0,
    diagnostic_policy: OverlapPolicy | None = None,
) -> list[StressPoint]:
    """Run the stress sweep; ``catastrophic_error`` is an absolute error threshold."""
    points: list[StressPoint] = []
    for strength in strengths:
        config = ObservationalConfig(n=n, confounding_strength=strength)
        statuses: Counter[str] = Counter()
        errors: list[float] = []
        refused = failed = catastrophic = unflagged = 0
        for rep in range(n_replicates):
            rep_seed = derive_seed(seed, f"overlap:{strength}:{rep}")
            ds = simulate(config, rep_seed)
            try:
                ps = estimate_propensity(ds.data, treatment, covariates)
                status = check_overlap(ps, estimand.type, diagnostic_policy).status.value
            except ConvergenceError:
                status = "blocking"  # separation is the most extreme positivity failure
            statuses[status] += 1
            try:
                est = run_estimator(estimator(rep_seed), ds.data, estimand)
            except (OverlapRefusedError, ConvergenceError):
                refused += 1
                continue
            except (ValueError, RuntimeError):
                failed += 1
                continue
            error = est.estimate - ds.truth[estimand.type.value]
            errors.append(error)
            if abs(error) > catastrophic_error:
                catastrophic += 1
                unflagged += status == "pass"
        arr = np.array(errors)
        points.append(
            StressPoint(
                confounding_strength=strength,
                n_replicates=n_replicates,
                overlap_status=dict(statuses),
                n_refused=refused,
                n_failed=failed,
                bias=float(arr.mean()) if arr.size else None,
                rmse=float(np.sqrt(np.mean(arr**2))) if arr.size else None,
                max_abs_error=float(np.abs(arr).max()) if arr.size else None,
                n_catastrophic=catastrophic,
                n_catastrophic_unflagged=unflagged,
            )
        )
    return points
