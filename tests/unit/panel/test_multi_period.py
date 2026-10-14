"""Task 4.3: balanced-panel fixture matches the TWFE reference."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.estimators import run_estimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.multi_period import ComparisonGroup, SingleCohortDiD
from tests.unit.panel.test_did import ATT

SPEC = PanelSpec()
EST = SingleCohortDiD(SPEC)


def panel(
    rng: np.random.Generator,
    n: int = 300,
    periods: int = 6,
    start: int = 4,
    effects: tuple[float, ...] = (1.0, 2.0, 3.0),
    late_start: bool = False,
) -> pd.DataFrame:
    treated = rng.random(n) < 0.5
    level = rng.normal(0, 2, n) + 3.0 * treated
    time_fe = rng.normal(0, 1, periods + 1)
    rows = []
    for i in range(n):
        s = float(start) if treated[i] else np.nan
        if late_start and not treated[i] and i % 5 == 0:
            s = float(periods + 2)
        for t in range(1, periods + 1):
            eff = effects[t - start] if treated[i] and t >= start else 0.0
            rows.append(
                {
                    "unit_id": i,
                    "period": t,
                    "treatment_start": s,
                    "outcome": level[i] + time_fe[t] + eff + rng.normal(),
                }
            )
    return pd.DataFrame(rows)


def twfe_reference(df: pd.DataFrame) -> float:
    """Static TWFE coefficient via two-way demeaning on a balanced panel."""
    d = (df["period"] >= df["treatment_start"]).astype(float)
    y = df["outcome"]

    def demean(v: pd.Series) -> np.ndarray:
        unit = v.groupby(df["unit_id"]).transform("mean")
        time = v.groupby(df["period"]).transform("mean")
        return (v - unit - time + v.mean()).to_numpy()

    dd, yy = demean(d), demean(y)
    return float(dd @ yy / (dd @ dd))


def test_matches_twfe_reference(rng: np.random.Generator) -> None:
    data = panel(rng)
    out = run_estimator(EST, data, ATT)
    assert out.estimate == pytest.approx(twfe_reference(data), abs=1e-10)


def test_recovers_average_post_period_att(rng: np.random.Generator) -> None:
    out = run_estimator(EST, panel(rng, n=4000), ATT)
    assert abs(out.estimate - 2.0) < 4 * out.std_error  # mean of (1, 2, 3)
    assert out.details["n_pre_periods"] == 3 and out.details["n_post_periods"] == 3


def test_comparison_group_rule_is_explicit(rng: np.random.Generator) -> None:
    data = panel(rng, late_start=True)
    never = run_estimator(EST, data, ATT)
    not_yet = run_estimator(
        SingleCohortDiD(SPEC, comparison=ComparisonGroup.NOT_YET_TREATED), data, ATT
    )
    assert never.details["n_excluded_start_after_window"] > 0
    assert not_yet.n_control > never.n_control  # type: ignore[operator]
    assert not_yet.details["comparison_group"] == "not_yet_treated"


def test_staggered_adoption_refused(rng: np.random.Generator) -> None:
    data = panel(rng)
    starts = data.groupby("unit_id")["treatment_start"].first()
    first_treated = starts[starts == 4].index[0]
    data.loc[data.unit_id == first_treated, "treatment_start"] = 5.0
    with pytest.raises(ValueError, match="staggered adoption"):
        run_estimator(EST, data, ATT)


def test_unbalanced_panel_refused(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="balanced"):
        run_estimator(EST, panel(rng).drop(index=3), ATT)


@pytest.mark.simulation
def test_unbiased_with_nominal_coverage(rng: np.random.Generator) -> None:
    sims, covered, estimates = 200, 0, []
    for _ in range(sims):
        out = run_estimator(EST, panel(rng, n=200), ATT)
        estimates.append(out.estimate)
        covered += out.ci_lower <= 2.0 <= out.ci_upper
    assert abs(np.mean(estimates) - 2.0) < 4 * np.std(estimates) / np.sqrt(sims)
    assert 0.91 <= covered / sims <= 0.98
