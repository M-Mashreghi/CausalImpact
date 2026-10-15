"""Task 4.9: a known synthetic-control fixture reproduces the pre-period fit."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.domain import Estimand, EstimandType, TargetPopulation
from causalimpact.estimators import run_estimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.synthetic_control import (
    SyntheticControl,
    fit_synthetic,
    synthetic_control_diagnostic,
    synthetic_weights,
    wide_outcomes,
)

ATT = Estimand(
    estimand_id="att_outcome",
    type=EstimandType.ATT,
    treatment="treatment_start",
    outcome="outcome",
    target_population=TargetPopulation(name="treated unit", description="the treated unit"),
)
SC = SyntheticControl()


def panel(
    rng: np.random.Generator,
    *,
    n_donors: int = 20,
    periods: int = 20,
    t0: int = 14,
    effect: float = 3.0,
    noise: float = 0.05,
    own_sd: float = 1.0,
    treated_weights: dict[int, float] | None = None,
) -> pd.DataFrame:
    """Donors: common factors plus idiosyncratic random walks (so weights are identified);
    the treated unit is a convex mix of donors."""
    factors = np.cumsum(rng.normal(0, 1, (periods, 2)), axis=0)
    loadings = rng.normal(1, 0.5, (n_donors, 2))
    own = np.cumsum(rng.normal(0, own_sd, (periods, n_donors)), axis=0)
    donors = factors @ loadings.T + own + rng.normal(0, noise, (periods, n_donors))
    mix = treated_weights or {0: 0.6, 1: 0.4}
    treated = sum(w * donors[:, j] for j, w in mix.items()) + rng.normal(0, noise, periods)
    t = np.arange(1, periods + 1)
    treated = treated + effect * (t >= t0)
    rows = [
        {"unit_id": "treated", "period": int(p), "treatment_start": float(t0), "outcome": y}
        for p, y in zip(t, treated, strict=True)
    ]
    for j in range(n_donors):
        rows += [
            {"unit_id": f"d{j:02d}", "period": int(p), "treatment_start": np.nan, "outcome": y}
            for p, y in zip(t, donors[:, j], strict=True)
        ]
    return pd.DataFrame(rows)


def test_known_mixture_recovers_weights_fit_and_effect(rng: np.random.Generator) -> None:
    out = run_estimator(SC, panel(rng), ATT)
    w = out.details["weights"]
    assert w["d00"] == pytest.approx(0.6, abs=0.05)  # type: ignore[index]
    assert w["d01"] == pytest.approx(0.4, abs=0.05)  # type: ignore[index]
    assert out.details["pre_rmspe"] < 0.1
    assert out.estimate == pytest.approx(3.0, abs=0.15)
    assert out.p_value == pytest.approx(1 / 21)  # treated ranks first among 21 units
    # Placebos fit far worse than the (exact-mixture) treated unit, so the interval falls
    # back to all placebos and is deliberately conservative.
    assert "conservative" in str(out.details["interval_placebo_rule"])
    assert out.ci_lower <= out.estimate <= out.ci_upper


def test_interval_excludes_zero_when_placebos_fit_well(rng: np.random.Generator) -> None:
    """Donors spanned by common factors: placebos fit well and the null spread is small."""
    out = run_estimator(SC, panel(rng, own_sd=0.0, noise=0.1, effect=3.0), ATT)
    assert "pre-RMSPE" in str(out.details["interval_placebo_rule"])
    assert out.ci_lower > 0


def test_weights_are_convex_and_exact_on_toy() -> None:
    donors = np.array([[1.0, 3.0], [2.0, 4.0], [3.0, 5.0]])  # periods x donors
    treated = 0.25 * donors[:, 0] + 0.75 * donors[:, 1]
    w = synthetic_weights(treated, donors)
    np.testing.assert_allclose(w, [0.25, 0.75], atol=1e-6)
    assert w.min() >= 0 and w.sum() == pytest.approx(1.0)


def test_path_and_gaps_are_reported(rng: np.random.Generator) -> None:
    out = run_estimator(SC, panel(rng), ATT)
    path = out.details["path"]
    assert len(path) == 20  # type: ignore[arg-type]
    post = [p["gap"] for p in path if p["period"] >= 14]  # type: ignore[index,union-attr]
    assert np.mean(post) == pytest.approx(out.estimate)


def test_null_effect_is_not_significant(rng: np.random.Generator) -> None:
    p_values = [
        run_estimator(SC, panel(rng, effect=0.0, noise=0.3), ATT).p_value for _ in range(10)
    ]
    assert np.mean([p is not None and p < 0.1 for p in p_values]) <= 0.3


def test_poor_fit_and_small_pool_are_flagged(rng: np.random.Generator) -> None:
    data = panel(rng, n_donors=3)
    wide = wide_outcomes(data, PanelSpec())
    wide.index = wide.index.map(str)
    # Treated unit far outside every donor's range: no convex combination fits.
    wide.loc["treated"] = wide.loc["treated"] + 100.0
    fit = fit_synthetic(wide, "treated", ["d00", "d01", "d02"], 14)
    diag = synthetic_control_diagnostic(fit, ["d00", "d01", "d02"], [])
    assert diag.status is DiagnosticStatus.BLOCKING
    assert {"small_donor_pool", "poor_pre_treatment_fit"} <= diag.codes()


def test_refuses_multiple_treated_units(rng: np.random.Generator) -> None:
    data = panel(rng)
    data.loc[data.unit_id == "d05", "treatment_start"] = 10.0
    with pytest.raises(ValueError, match="exactly one treated unit"):
        run_estimator(SC, data, ATT)


def test_incomplete_donors_are_excluded_and_reported(rng: np.random.Generator) -> None:
    data = panel(rng)
    data.loc[(data.unit_id == "d07") & (data.period == 3), "outcome"] = np.nan
    out = run_estimator(SC, data, ATT)
    assert out.details["donors_excluded_incomplete"] == ["d07"]
    assert "d07" not in out.details["weights"]  # type: ignore[operator]


def test_deterministic(rng: np.random.Generator) -> None:
    data = panel(rng)
    assert run_estimator(SC, data, ATT) == run_estimator(SC, data, ATT)
