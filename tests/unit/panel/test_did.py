"""Task 4.2: a known-effect 2x2 DGP is recovered."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import Estimand, EstimandMismatchError, EstimandType, TargetPopulation
from causalimpact.estimators import run_estimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.did import TwoPeriodDiD

SPEC = PanelSpec()
ATT = Estimand(
    estimand_id="att_outcome",
    type=EstimandType.ATT,
    treatment="treatment_start",
    outcome="outcome",
    target_population=TargetPopulation(name="units", description="Treated units"),
)
DID = TwoPeriodDiD(SPEC, pre_period=1, post_period=2)


def two_period(
    rng: np.random.Generator, n: int = 400, effect: float = 2.0, trend_gap: float = 0.0
) -> pd.DataFrame:
    """Units with level differences (selection on levels) and a common trend."""
    treated = rng.random(n) < 0.4
    level = rng.normal(0, 3, n) + 5.0 * treated  # treated units start higher
    rows = []
    for i in range(n):
        for t in (1, 2):
            trend = 1.5 * (t - 1) + trend_gap * treated[i] * (t - 1)
            y = level[i] + trend + effect * (treated[i] and t == 2) + rng.normal()
            rows.append(
                {
                    "unit_id": i,
                    "period": t,
                    "treatment_start": 2.0 if treated[i] else np.nan,
                    "outcome": y,
                }
            )
    return pd.DataFrame(rows)


def test_hand_computed_components() -> None:
    df = pd.DataFrame(
        {
            "unit_id": [1, 1, 2, 2, 3, 3, 4, 4],
            "period": [1, 2] * 4,
            "treatment_start": [2, 2, 2, 2, np.nan, np.nan, np.nan, np.nan],
            "outcome": [10, 15, 12, 19, 3, 4, 5, 8],
        }
    )
    out = run_estimator(DID, df, ATT)
    # treated change: (5 + 7)/2 = 6; comparison change: (1 + 3)/2 = 2
    assert out.estimate == pytest.approx(4.0)
    assert out.details["group_period_means"] == {
        "treated_pre": 11.0,
        "treated_post": 17.0,
        "comparison_pre": 4.0,
        "comparison_post": 6.0,
    }
    assert out.std_error == pytest.approx(np.sqrt(2.0 / 2 + 2.0 / 2))


def test_known_effect_recovered_despite_level_selection(rng: np.random.Generator) -> None:
    data = two_period(rng, n=4000)
    out = run_estimator(DID, data, ATT)
    assert abs(out.estimate - 2.0) < 4 * out.std_error
    naive_post = data[data.period == 2].groupby(data.treatment_start.notna())["outcome"].mean()
    assert naive_post[True] - naive_post[False] > 5  # cross-sectional contrast is biased


def test_parallel_trend_violation_biases_estimate(rng: np.random.Generator) -> None:
    out = run_estimator(DID, two_period(rng, n=4000, trend_gap=1.0), ATT)
    assert out.estimate == pytest.approx(3.0, abs=0.15)  # effect + trend gap: not identified


def test_only_att_supported(rng: np.random.Generator) -> None:
    ate = ATT.model_copy(update={"type": EstimandType.ATE})
    with pytest.raises(EstimandMismatchError):
        run_estimator(DID, two_period(rng, n=50), ate)


def test_pre_treated_units_refused(rng: np.random.Generator) -> None:
    data = two_period(rng, n=50)
    data.loc[data.unit_id == 0, "treatment_start"] = 1.0
    with pytest.raises(ValueError, match="at or before the pre period"):
        run_estimator(DID, data, ATT)


def test_missing_period_refused(rng: np.random.Generator) -> None:
    data = two_period(rng, n=50)
    with pytest.raises(ValueError, match="both periods"):
        run_estimator(DID, data.drop(index=0), ATT)


def test_invalid_timing_refused(rng: np.random.Generator) -> None:
    data = two_period(rng, n=50)
    with pytest.raises(ValueError, match="duplicate_unit_period"):
        run_estimator(DID, pd.concat([data, data.iloc[[0]]]), ATT)


@pytest.mark.simulation
def test_unbiased_with_nominal_coverage(rng: np.random.Generator) -> None:
    sims, estimates, covered = 300, [], 0
    for _ in range(sims):
        out = run_estimator(DID, two_period(rng, n=300), ATT)
        estimates.append(out.estimate)
        covered += out.ci_lower <= 2.0 <= out.ci_upper
    assert abs(np.mean(estimates) - 2.0) < 4 * np.std(estimates) / np.sqrt(sims)
    assert 0.92 <= covered / sims <= 0.98
