"""Task 3.2: propensity scores are bounded, correct and reproducible."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import optimize

from causalimpact.domain import CovariateDType, CovariateSpec, TreatmentSpec, TriState
from causalimpact.observational.propensity import (
    ConvergenceError,
    LogisticPropensity,
    estimate_propensity,
)

TREATMENT = TreatmentSpec(name="treated")


def cov(name: str, dtype: CovariateDType = CovariateDType.NUMERIC) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="baseline",
        pre_treatment=TriState.TRUE,
        descendant_of_treatment=TriState.FALSE,
    )


COVS = (cov("x1"), cov("x2"), cov("region", CovariateDType.CATEGORICAL))
TRUE_COEF = {"intercept": -0.5, "x1": 1.0, "x2": -0.7}


def confounded(rng: np.random.Generator, n: int = 5000) -> pd.DataFrame:
    x1 = rng.normal(size=n)
    x2 = rng.normal(2.0, 3.0, size=n)
    region = rng.choice(["a", "b"], size=n)
    logit = (
        TRUE_COEF["intercept"]
        + TRUE_COEF["x1"] * x1
        + TRUE_COEF["x2"] * (x2 - 2.0) / 3.0
        + 0.4 * (region == "b")
    )
    t = rng.binomial(1, 1 / (1 + np.exp(-logit)))
    return pd.DataFrame(
        {"unit_id": np.arange(n), "treated": t, "x1": x1, "x2": x2, "region": region}
    )


def test_scores_bounded_and_persisted(rng: np.random.Generator) -> None:
    ps = estimate_propensity(confounded(rng), TREATMENT, COVS)
    assert np.all((ps.scores > 0) & (ps.scores < 1))
    frame = ps.to_frame()
    assert list(frame.columns) == ["unit_id", "treated", "propensity"]
    cfg = ps.nuisance_config
    assert cfg["model"] == "logistic_regression_irls"
    assert cfg["covariates"] == ["x1", "x2", "region"]
    assert cfg["design_columns"] == ["x1", "x2", "region==b"]
    assert ps.fingerprint.startswith("sha256:")


def test_recovers_true_coefficients(rng: np.random.Generator) -> None:
    data = confounded(rng, n=40_000)
    coefs = estimate_propensity(data, TREATMENT, COVS).nuisance_config["coefficients"]
    assert coefs["x1"] == pytest.approx(1.0, abs=0.05)  # type: ignore[index,call-overload]
    assert coefs["x2"] == pytest.approx(-0.7 / 3.0, abs=0.02)  # type: ignore[index,call-overload]
    assert coefs["region==b"] == pytest.approx(0.4, abs=0.06)  # type: ignore[index,call-overload]


def test_matches_independent_maximum_likelihood(rng: np.random.Generator) -> None:
    data = confounded(rng, n=2000)
    t = data["treated"].to_numpy(dtype=float)
    x = np.column_stack([np.ones(len(data)), data["x1"], data["x2"]])

    def negloglik(beta: np.ndarray) -> float:
        z = x @ beta
        return float(np.sum(np.logaddexp(0, z) - t * z))

    reference = optimize.minimize(negloglik, np.zeros(3), method="BFGS", tol=1e-10).x
    ps = estimate_propensity(data, TREATMENT, COVS[:2])
    expected = 1 / (1 + np.exp(-(x @ reference)))
    np.testing.assert_allclose(ps.scores, expected, atol=1e-6)


def test_reproducible_and_row_order_invariant(rng: np.random.Generator) -> None:
    data = confounded(rng, n=1000)
    a = estimate_propensity(data, TREATMENT, COVS)
    b = estimate_propensity(data, TREATMENT, COVS)
    np.testing.assert_array_equal(a.scores, b.scores)
    assert a.fingerprint == b.fingerprint
    shuffled = data.sample(frac=1.0, random_state=3)
    c = estimate_propensity(shuffled, TREATMENT, COVS).to_frame().set_index("unit_id")
    np.testing.assert_allclose(c.loc[data["unit_id"], "propensity"].to_numpy(), a.scores, rtol=1e-9)


def test_penalty_changes_config_fingerprint(rng: np.random.Generator) -> None:
    data = confounded(rng, n=500)
    plain = estimate_propensity(data, TREATMENT, COVS)
    ridge = estimate_propensity(data, TREATMENT, COVS, model=LogisticPropensity(l2_penalty=5.0))
    assert ridge.fingerprint != plain.fingerprint
    assert np.ptp(ridge.scores) < np.ptp(plain.scores)  # shrinkage toward the mean


def test_complete_separation_raises() -> None:
    data = pd.DataFrame(
        {"unit_id": range(40), "x1": np.arange(40.0), "treated": [0] * 20 + [1] * 20}
    )
    with pytest.raises(ConvergenceError, match="separation"):
        estimate_propensity(data, TREATMENT, (cov("x1"),))


def test_penalty_resolves_separation() -> None:
    data = pd.DataFrame(
        {"unit_id": range(40), "x1": np.arange(40.0), "treated": [0] * 20 + [1] * 20}
    )
    ps = estimate_propensity(data, TREATMENT, (cov("x1"),), model=LogisticPropensity(1.0))
    assert np.all((ps.scores > 0) & (ps.scores < 1))


@pytest.mark.parametrize(
    ("mutate", "msg"),
    [
        (lambda d: d.assign(treated=0), "both treatment groups"),
        (lambda d: d.assign(x1=1.0), "constant covariates"),
        (lambda d: d.assign(treated=d.treated.replace(1, 2)), "declared levels"),
    ],
)
def test_invalid_inputs(rng: np.random.Generator, mutate: object, msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        estimate_propensity(mutate(confounded(rng, n=200)), TREATMENT, COVS)  # type: ignore[operator]


def test_post_treatment_covariate_refused(rng: np.random.Generator) -> None:
    post = CovariateSpec(
        name="x1",
        dtype=CovariateDType.NUMERIC,
        pre_treatment=TriState.FALSE,
        descendant_of_treatment=TriState.TRUE,
    )
    with pytest.raises(ValueError, match="not eligible"):
        estimate_propensity(confounded(rng, n=200), TREATMENT, (post,))
