"""Task 3.6: a known linear DGP is recovered by outcome regression."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.domain import EstimandMismatchError, EstimandType
from causalimpact.estimators import run_estimator
from causalimpact.observational.outcome_regression import (
    LinearOutcomeModel,
    OutcomeRegressionEstimator,
    fit_outcome_nuisance,
    g_computation,
)
from tests.unit.observational.test_weighting import TREATMENT, X, dgp, estimand


def est(n_bootstrap: int = 100, seed: int = 3) -> OutcomeRegressionEstimator:
    return OutcomeRegressionEstimator(TREATMENT, (X,), seed=seed, n_bootstrap=n_bootstrap)


def test_nuisance_is_separate_from_effect(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=2000, hetero=1.0)
    x = data[["x"]].to_numpy()
    y, t = data["y"].to_numpy(), data["treated"].to_numpy(dtype=float)
    nuisance = fit_outcome_nuisance(LinearOutcomeModel(), x, y, t)
    # mu_1(x) = 3 + 4x, mu_0(x) = 1 + 3x in the DGP.
    np.testing.assert_allclose(nuisance.treated_model.coef, [3.0, 4.0], atol=0.1)  # type: ignore[attr-defined]
    np.testing.assert_allclose(nuisance.control_model.coef, [1.0, 3.0], atol=0.1)  # type: ignore[attr-defined]
    assert not hasattr(nuisance, "estimate")


@pytest.mark.parametrize("kind", [EstimandType.ATE, EstimandType.ATT, EstimandType.ATC])
def test_linear_dgp_recovers_each_estimand(rng: np.random.Generator, kind: EstimandType) -> None:
    data, truth = dgp(rng, n=20_000, hetero=1.0)
    out = run_estimator(est(n_bootstrap=60), data, estimand(kind))
    assert out.estimate == pytest.approx(truth[kind.value], abs=0.06)
    # One draw: allow 4 SE (nominal coverage is checked by the simulation test below).
    assert abs(out.estimate - truth[kind.value]) < 4 * out.std_error
    assert out.details["outcome_learner"] == {"model": "ols_linear"}


def test_g_computation_formulas_on_toy_data() -> None:
    class Const:
        def __init__(self, v: float) -> None:
            self.v = v

        def predict(self, x: np.ndarray) -> np.ndarray:
            return np.full(len(x), self.v)

    from causalimpact.observational.outcome_regression import OutcomeNuisance

    nuisance = OutcomeNuisance(Const(5.0), Const(2.0), {"model": "const"})
    x = np.zeros((4, 1))
    y = np.array([6.0, 4.0, 1.0, 3.0])
    t = np.array([1.0, 1.0, 0.0, 0.0])
    assert g_computation(nuisance, x, y, t, EstimandType.ATE) == pytest.approx(3.0)
    assert g_computation(nuisance, x, y, t, EstimandType.ATT) == pytest.approx(5.0 - 2.0)
    assert g_computation(nuisance, x, y, t, EstimandType.ATC) == pytest.approx(5.0 - 2.0)


def test_poor_overlap_is_surfaced_not_hidden(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=1500, strength=6.0)
    out = run_estimator(est(n_bootstrap=50), data, estimand(EstimandType.ATE))
    assert out.details["overlap_status"] == "blocking"
    assert out.details["overlap_findings"]


def test_ato_is_not_supported(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=200)
    with pytest.raises(EstimandMismatchError, match="cannot target ATO"):
        run_estimator(est(), data, estimand(EstimandType.ATO))


def test_bootstrap_reproducible(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=500)
    target = estimand(EstimandType.ATE)
    a = run_estimator(est(seed=1), data, target)
    b = run_estimator(est(seed=1), data, target)
    assert a.std_error == b.std_error


@pytest.mark.simulation
def test_coverage_near_nominal(rng: np.random.Generator) -> None:
    sims, covered = 150, 0
    for _ in range(sims):
        data, truth = dgp(rng, n=1000, hetero=1.0)
        out = run_estimator(est(n_bootstrap=100), data, estimand(EstimandType.ATE))
        covered += out.ci_lower <= truth["ATE"] <= out.ci_upper
    assert 0.89 <= covered / sims <= 0.99
