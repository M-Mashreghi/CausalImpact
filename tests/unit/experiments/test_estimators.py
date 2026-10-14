"""Task 2.4: difference in means / proportions are unbiased with sensible CIs."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from causalimpact.domain import (
    Estimand,
    EstimandMismatchError,
    EstimandType,
    TargetPopulation,
    TreatmentBasis,
    TreatmentSpec,
)
from causalimpact.estimators import run_estimator
from causalimpact.experiments.estimators import DifferenceInMeans, DifferenceInProportions

TREATMENT = TreatmentSpec(name="arm", control_value="control", treated_value="treatment")
POP = TargetPopulation(name="users", description="Users in the experiment")
ITT = Estimand(
    estimand_id="itt_y",
    type=EstimandType.ITT,
    treatment="arm",
    outcome="y",
    target_population=POP,
    treatment_basis=TreatmentBasis.ASSIGNMENT,
)
DIM = DifferenceInMeans(TREATMENT)
DIP = DifferenceInProportions(TREATMENT)


def frame(treated: list[float], control: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "arm": ["treatment"] * len(treated) + ["control"] * len(control),
            "y": treated + control,
        }
    )


def simulate(rng: np.random.Generator, n: int, effect: float, binary: bool) -> pd.DataFrame:
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    if binary:
        p = np.where(arm == "treatment", 0.10 + effect, 0.10)
        y = rng.binomial(1, p).astype(float)
    else:
        y = rng.normal(5.0, 2.0, n) + effect * (arm == "treatment")
    return pd.DataFrame({"arm": arm, "y": y})


class TestHandComputed:
    def test_difference_in_means_matches_welch(self) -> None:
        out = run_estimator(DIM, frame([3, 5, 7, 9], [1, 2, 3]), ITT)
        assert out.estimate == pytest.approx(4.0)
        assert out.std_error == pytest.approx(math.sqrt(20 / 12 + 1 / 3))
        v1, v0 = 20 / 12, 1 / 3
        df = (v1 + v0) ** 2 / (v1**2 / 3 + v0**2 / 2)
        assert out.degrees_of_freedom == pytest.approx(df)
        half = stats.t.ppf(0.975, df) * math.sqrt(2.0)
        assert (out.ci_lower, out.ci_upper) == pytest.approx((4 - half, 4 + half))
        assert (out.n_treated, out.n_control, out.n_units) == (4, 3, 7)
        # Agrees with scipy's Welch test.
        ref = stats.ttest_ind([3, 5, 7, 9], [1, 2, 3], equal_var=False)
        assert out.p_value == pytest.approx(ref.pvalue)

    def test_difference_in_proportions_matches_wald(self) -> None:
        out = run_estimator(DIP, frame([1, 1, 1, 0], [1, 0, 0, 0, 0]), ITT, confidence_level=0.9)
        se = math.sqrt(0.75 * 0.25 / 4 + 0.2 * 0.8 / 5)
        assert out.estimate == pytest.approx(0.55)
        assert out.std_error == pytest.approx(se)
        z = stats.norm.ppf(0.95)
        assert (out.ci_lower, out.ci_upper) == pytest.approx((0.55 - z * se, 0.55 + z * se))
        assert out.confidence_level == 0.9


class TestRefusals:
    def test_ate_estimand_refused(self) -> None:
        ate = ITT.model_copy(
            update={"type": EstimandType.ATE, "treatment_basis": TreatmentBasis.RECEIPT}
        )
        with pytest.raises(EstimandMismatchError, match="cannot target ATE"):
            run_estimator(DIM, frame([1, 2], [3, 4]), ate)

    def test_missing_outcomes_refused(self) -> None:
        with pytest.raises(ValueError, match="missing outcomes"):
            run_estimator(DIM, frame([1, 2, float("nan")], [3, 4]), ITT)

    def test_unknown_arm_refused(self) -> None:
        data = frame([1, 2], [3, 4])
        data.loc[0, "arm"] = "holdout"
        with pytest.raises(ValueError, match="unexpected treatment"):
            run_estimator(DIM, data, ITT)

    def test_tiny_arm_refused(self) -> None:
        with pytest.raises(ValueError, match="at least two"):
            run_estimator(DIM, frame([1], [3, 4]), ITT)

    def test_non_binary_outcome_refused_for_proportions(self) -> None:
        with pytest.raises(ValueError, match="0/1"):
            run_estimator(DIP, frame([1, 2], [0, 1]), ITT)

    def test_degenerate_proportions_refused(self) -> None:
        with pytest.raises(ValueError, match="degenerate"):
            run_estimator(DIP, frame([1, 1], [0, 0]), ITT)

    def test_treatment_column_must_match_estimand(self) -> None:
        other = DifferenceInMeans(TreatmentSpec(name="variant"))
        with pytest.raises(ValueError, match="treatment column"):
            run_estimator(other, frame([1, 2], [3, 4]), ITT)


@pytest.mark.simulation
@pytest.mark.parametrize(
    ("estimator", "effect", "binary"),
    [(DIM, 0.5, False), (DIM, -0.3, False), (DIP, 0.03, True)],
)
def test_known_effect_is_recovered_without_bias(
    rng: np.random.Generator, estimator: DifferenceInMeans, effect: float, binary: bool
) -> None:
    estimates = [
        run_estimator(estimator, simulate(rng, 2000, effect, binary), ITT).estimate
        for _ in range(400)
    ]
    mc_se = np.std(estimates, ddof=1) / math.sqrt(len(estimates))
    assert abs(np.mean(estimates) - effect) < 4 * mc_se


@pytest.mark.simulation
@pytest.mark.parametrize(("estimator", "binary"), [(DIM, False), (DIP, True)])
def test_null_effect_ci_coverage_is_nominal(
    rng: np.random.Generator, estimator: DifferenceInMeans, binary: bool
) -> None:
    sims = 1000
    results = [run_estimator(estimator, simulate(rng, 2000, 0.0, binary), ITT) for _ in range(sims)]
    coverage = np.mean([r.ci_lower <= 0.0 <= r.ci_upper for r in results])
    # 95% CI; Monte Carlo SE of coverage ~0.007 at 1000 sims.
    assert 0.93 <= coverage <= 0.97
    type_one = np.mean([r.p_value is not None and r.p_value < 0.05 for r in results])
    assert type_one == pytest.approx(1 - coverage, abs=1e-9)
