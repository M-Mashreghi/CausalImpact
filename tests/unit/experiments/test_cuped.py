"""Task 2.6: a correlated pre-period metric reduces variance without bias."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.estimators import run_estimator
from causalimpact.experiments.cuped import CupedITT, cuped_theta
from tests.unit.experiments.test_estimators import DIM, ITT, TREATMENT


def pre_metric(
    pre: TriState = TriState.TRUE, desc: TriState = TriState.FALSE, name: str = "y_pre"
) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=CovariateDType.NUMERIC,
        measurement_time="14 days before assignment",
        pre_treatment=pre,
        descendant_of_treatment=desc,
    )


CUPED = CupedITT(TREATMENT, pre_metric())


def correlated(
    rng: np.random.Generator, n: int = 2000, rho: float = 0.8, effect: float = 0.2
) -> pd.DataFrame:
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    pre = rng.normal(10.0, 2.0, n)
    noise = rng.normal(0.0, 2.0 * math.sqrt(1 - rho**2), n)
    y = 10.0 + rho * (pre - 10.0) + noise + effect * (arm == "treatment")
    return pd.DataFrame({"arm": arm, "y_pre": pre, "y": y})


def test_variance_reduction_matches_correlation(rng: np.random.Generator) -> None:
    out = run_estimator(CUPED, correlated(rng, rho=0.8), ITT)
    # Theory: Var(CUPED) / Var(unadjusted) ~= 1 - rho^2 = 0.36.
    assert out.details["variance_ratio_vs_unadjusted"] == pytest.approx(0.36, abs=0.06)
    assert out.std_error < out.details["unadjusted_std_error"]  # type: ignore[operator]
    assert out.estimand_type is ITT.type
    assert out.inference_method == "cuped_pooled_theta_welch_t"


def test_theta_is_regression_slope(rng: np.random.Generator) -> None:
    data = correlated(rng)
    slope = np.polyfit(data["y_pre"], data["y"], 1)[0]
    assert cuped_theta(data["y"].to_numpy(), data["y_pre"].to_numpy()) == pytest.approx(slope)


def test_uncorrelated_pre_metric_does_not_help(rng: np.random.Generator) -> None:
    out = run_estimator(CUPED, correlated(rng, rho=0.0), ITT)
    assert out.details["variance_ratio_vs_unadjusted"] == pytest.approx(1.0, abs=0.02)


@pytest.mark.parametrize(
    ("spec", "msg"),
    [
        (pre_metric(pre=TriState.FALSE), "pre-treatment"),
        (pre_metric(pre=TriState.UNKNOWN), "pre-treatment"),
        (pre_metric(desc=TriState.UNKNOWN), "pre-treatment"),
    ],
)
def test_ineligible_pre_metric_refused(
    rng: np.random.Generator, spec: CovariateSpec, msg: str
) -> None:
    with pytest.raises(ValueError, match=msg):
        run_estimator(CupedITT(TREATMENT, spec), correlated(rng, n=100), ITT)


def test_outcome_cannot_be_its_own_pre_metric(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="different column"):
        run_estimator(CupedITT(TREATMENT, pre_metric(name="y")), correlated(rng, n=100), ITT)


def test_missing_and_constant_pre_metric_refused(rng: np.random.Generator) -> None:
    data = correlated(rng, n=100)
    with pytest.raises(ValueError, match="constant"):
        run_estimator(CUPED, data.assign(y_pre=1.0), ITT)
    data.loc[0, "y_pre"] = np.nan
    with pytest.raises(ValueError, match="missing"):
        run_estimator(CUPED, data, ITT)


@pytest.mark.simulation
def test_unbiased_with_nominal_coverage(rng: np.random.Generator) -> None:
    sims, effect = 500, 0.2
    cuped, plain = [], []
    for _ in range(sims):
        data = correlated(rng, n=1000, effect=effect)
        cuped.append(run_estimator(CUPED, data, ITT))
        plain.append(run_estimator(DIM, data, ITT).estimate)
    estimates = np.array([r.estimate for r in cuped])
    assert abs(estimates.mean() - effect) < 4 * estimates.std(ddof=1) / math.sqrt(sims)
    coverage = np.mean([r.ci_lower <= effect <= r.ci_upper for r in cuped])
    assert 0.92 <= coverage <= 0.98
    assert estimates.var() < 0.5 * np.var(plain)
