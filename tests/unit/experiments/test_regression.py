"""Task 2.5: adjustment improves precision on a prognostic fixture without bias."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    MissingnessPolicy,
    TriState,
)
from causalimpact.estimators import run_estimator
from causalimpact.estimators.ols import ols_hc2
from causalimpact.experiments.regression import RegressionAdjustedITT
from tests.unit.experiments.test_estimators import DIM, ITT, TREATMENT


def cov(
    name: str,
    dtype: CovariateDType = CovariateDType.NUMERIC,
    *,
    pre: TriState = TriState.TRUE,
    missing: MissingnessPolicy = MissingnessPolicy.FORBID,
) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="pre-assignment",
        pre_treatment=pre,
        descendant_of_treatment=TriState.FALSE,
        missingness_policy=missing,
    )


LIN = RegressionAdjustedITT(TREATMENT, (cov("x"), cov("segment", CovariateDType.CATEGORICAL)))


def prognostic(
    rng: np.random.Generator, n: int = 1000, effect: float = 1.0, heterogeneity: float = 0.0
) -> pd.DataFrame:
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    t = (arm == "treatment").astype(float)
    x = rng.normal(0.0, 1.0, n)
    segment = rng.choice(["a", "b", "c"], n)
    seg_shift = pd.Series(segment).map({"a": 0.0, "b": 1.0, "c": -1.0}).to_numpy()
    # Heterogeneous effect has mean `effect` because E[x] = 0.
    y = 3.0 * x + seg_shift + t * (effect + heterogeneity * x) + rng.normal(0.0, 1.0, n)
    return pd.DataFrame({"arm": arm, "x": x, "segment": segment, "y": y})


def test_hc2_without_covariates_equals_neyman_variance(rng: np.random.Generator) -> None:
    t = np.repeat([0.0, 1.0], [30, 50])
    y = rng.normal(size=80) + t
    fit = ols_hc2(np.column_stack([np.ones_like(t), t]), y)
    y1, y0 = y[t == 1], y[t == 0]
    assert fit.coef[1] == pytest.approx(y1.mean() - y0.mean())
    assert fit.cov[1, 1] == pytest.approx(y1.var(ddof=1) / 50 + y0.var(ddof=1) / 30)


def test_adjustment_shrinks_standard_error(rng: np.random.Generator) -> None:
    data = prognostic(rng)
    unadjusted = run_estimator(DIM, data, ITT)
    adjusted = run_estimator(LIN, data, ITT)
    assert adjusted.std_error < 0.5 * unadjusted.std_error
    assert adjusted.ci_lower <= 1.0 <= adjusted.ci_upper
    assert adjusted.estimand_type is unadjusted.estimand_type  # same ITT estimand


def test_coefficient_matches_direct_least_squares(rng: np.random.Generator) -> None:
    data = prognostic(rng, n=200)
    out = run_estimator(RegressionAdjustedITT(TREATMENT, (cov("x"),)), data, ITT)
    t = (data["arm"] == "treatment").to_numpy(dtype=float)
    xc = data["x"].to_numpy() - data["x"].mean()
    design = np.column_stack([np.ones_like(t), t, xc, xc * t])
    coef, *_ = np.linalg.lstsq(design, data["y"].to_numpy(), rcond=None)
    assert out.estimate == pytest.approx(coef[1])


def test_post_treatment_covariate_refused(rng: np.random.Generator) -> None:
    est = RegressionAdjustedITT(TREATMENT, (cov("x", pre=TriState.FALSE),))
    with pytest.raises(ValueError, match="not eligible"):
        run_estimator(est, prognostic(rng, n=50), ITT)


def test_outcome_as_covariate_refused(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="outcome cannot"):
        run_estimator(RegressionAdjustedITT(TREATMENT, (cov("y"),)), prognostic(rng, n=50), ITT)


def test_missing_covariate_requires_indicator_policy(rng: np.random.Generator) -> None:
    data = prognostic(rng, n=200)
    data.loc[:9, "x"] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        run_estimator(RegressionAdjustedITT(TREATMENT, (cov("x"),)), data, ITT)
    est = RegressionAdjustedITT(TREATMENT, (cov("x", missing=MissingnessPolicy.INDICATOR),))
    assert math.isfinite(run_estimator(est, data, ITT).estimate)


def test_constant_covariate_is_rank_deficient(rng: np.random.Generator) -> None:
    data = prognostic(rng, n=100).assign(x=1.0)
    with pytest.raises(ValueError, match="rank deficient"):
        run_estimator(RegressionAdjustedITT(TREATMENT, (cov("x"),)), data, ITT)


@pytest.mark.simulation
@pytest.mark.parametrize("heterogeneity", [0.0, 1.5])
def test_unbiased_with_nominal_coverage_and_better_precision(
    rng: np.random.Generator, heterogeneity: float
) -> None:
    sims, effect = 400, 1.0
    adjusted, unadjusted = [], []
    for _ in range(sims):
        data = prognostic(rng, n=400, effect=effect, heterogeneity=heterogeneity)
        adjusted.append(run_estimator(LIN, data, ITT))
        unadjusted.append(run_estimator(DIM, data, ITT).estimate)
    estimates = np.array([r.estimate for r in adjusted])
    mc_se = estimates.std(ddof=1) / math.sqrt(sims)
    assert abs(estimates.mean() - effect) < 4 * mc_se
    coverage = np.mean([r.ci_lower <= effect <= r.ci_upper for r in adjusted])
    assert 0.92 <= coverage <= 0.98
    assert estimates.var() < 0.25 * np.var(unadjusted)
