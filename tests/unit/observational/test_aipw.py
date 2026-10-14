"""Task 3.7: AIPW stays approximately unbiased when one nuisance model is correct."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import EstimandMismatchError, EstimandType
from causalimpact.estimators import run_estimator
from causalimpact.observational.aipw import AIPWEstimator, aipw_scores
from causalimpact.observational.outcome_regression import OutcomeRegressionEstimator
from causalimpact.observational.overlap import OverlapRefusedError
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme
from tests.unit.observational.test_weighting import TREATMENT, X, dgp, estimand

AIPW = AIPWEstimator(TREATMENT, (X,))
ATE = estimand(EstimandType.ATE)


def outcome_misspecified(rng: np.random.Generator, n: int = 3000) -> pd.DataFrame:
    """Propensity is logistic-linear in x (correct); outcome is exp(1.2 x) (linear model wrong)."""
    x = rng.normal(size=n)
    t = rng.binomial(1, 1 / (1 + np.exp(-x)))
    y = 1 + np.exp(1.2 * x) + 1.0 * t + rng.normal(size=n)
    return pd.DataFrame({"unit_id": np.arange(n), "treated": t, "x": x, "y": y})


def propensity_misspecified(rng: np.random.Generator, n: int = 3000) -> pd.DataFrame:
    """Outcome is linear in x (correct); the true propensity logit is quadratic."""
    x = rng.normal(size=n)
    t = rng.binomial(1, 1 / (1 + np.exp(-(-0.3 + 1.2 * x - 0.8 * x**2))))
    y = 1 + 2 * x + 1.0 * t + rng.normal(size=n)
    return pd.DataFrame({"unit_id": np.arange(n), "treated": t, "x": x, "y": y})


def test_reduces_to_ipw_when_outcome_model_is_zero() -> None:
    y = np.array([3.0, 1.0, 2.0, 0.5])
    t = np.array([1.0, 0.0, 1.0, 0.0])
    e = np.array([0.5, 0.25, 0.8, 0.4])
    tau, influence = aipw_scores(EstimandType.ATE, y, t, e, np.zeros(4), np.zeros(4))
    ht = np.mean(t * y / e - (1 - t) * y / (1 - e))
    assert tau == pytest.approx(ht)
    assert influence.mean() == pytest.approx(0.0, abs=1e-12)


def test_reduces_to_g_computation_when_residuals_vanish() -> None:
    mu1, mu0 = np.array([3.0, 4.0, 5.0]), np.array([1.0, 1.5, 2.0])
    t = np.array([1.0, 0.0, 1.0])
    y = np.where(t == 1, mu1, mu0)
    tau, _ = aipw_scores(EstimandType.ATE, y, t, np.full(3, 0.5), mu1, mu0)
    assert tau == pytest.approx(np.mean(mu1 - mu0))


def test_correct_models_recover_ate_and_att(rng: np.random.Generator) -> None:
    data, truth = dgp(rng, n=20_000, hetero=1.0)
    ate = run_estimator(AIPW, data, ATE)
    att = run_estimator(AIPW, data, estimand(EstimandType.ATT))
    assert abs(ate.estimate - truth["ATE"]) < 4 * ate.std_error
    assert abs(att.estimate - truth["ATT"]) < 4 * att.std_error
    assert ate.details["cross_fitting"] is False


def test_poor_overlap_refused(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=1500, strength=6.0)
    with pytest.raises(OverlapRefusedError):
        run_estimator(AIPW, data, ATE)


def test_atc_not_supported(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=300)
    with pytest.raises(EstimandMismatchError, match="cannot target ATC"):
        run_estimator(AIPW, data, estimand(EstimandType.ATC))


def test_deterministic(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=500)
    assert run_estimator(AIPW, data, ATE) == run_estimator(AIPW, data, ATE)


def _bias(
    rng: np.random.Generator,
    make: Callable[[np.random.Generator], pd.DataFrame],
    est: object,
    sims: int,
) -> tuple[float, float]:
    errors = [run_estimator(est, make(rng), ATE).estimate - 1.0 for _ in range(sims)]  # type: ignore[arg-type]
    return float(np.mean(errors)), float(np.std(errors, ddof=1) / np.sqrt(sims))


@pytest.mark.simulation
def test_double_robustness_outcome_model_wrong(rng: np.random.Generator) -> None:
    sims = 60
    aipw_bias, aipw_mc = _bias(rng, outcome_misspecified, AIPW, sims)
    reg = OutcomeRegressionEstimator(TREATMENT, (X,), seed=1, n_bootstrap=50)
    reg_bias, reg_mc = _bias(rng, outcome_misspecified, reg, sims)
    assert abs(aipw_bias) < 4 * aipw_mc + 0.03
    assert abs(reg_bias) > 4 * reg_mc  # the misspecification matters for regression alone


@pytest.mark.simulation
def test_double_robustness_propensity_model_wrong(rng: np.random.Generator) -> None:
    sims = 60
    aipw_bias, aipw_mc = _bias(rng, propensity_misspecified, AIPW, sims)
    ipw = WeightingEstimator(TREATMENT, (X,), WeightScheme.IPW, seed=1, n_bootstrap=50)
    ipw_bias, ipw_mc = _bias(rng, propensity_misspecified, ipw, sims)
    assert abs(aipw_bias) < 4 * aipw_mc + 0.02
    assert abs(ipw_bias) > 4 * ipw_mc  # the misspecification matters for IPW alone


@pytest.mark.simulation
def test_influence_function_coverage(rng: np.random.Generator) -> None:
    sims, covered = 300, 0
    for _ in range(sims):
        data, _ = dgp(rng, n=1500, hetero=1.0)
        out = run_estimator(AIPW, data, ATE)
        # The influence-function SE targets the population ATE, which is exactly 2 in
        # this DGP (E[x] = 0); it is conservative for the sample-average effect.
        covered += out.ci_lower <= 2.0 <= out.ci_upper
    assert 0.91 <= covered / sims <= 0.98
