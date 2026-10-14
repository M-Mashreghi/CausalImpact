"""Task 4.4: relative-time indexing is correct; staggered use is flagged."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.estimators.ols import ols_cluster_robust, two_way_demean
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.event_study import relative_time, twfe_event_study

SPEC = PanelSpec()
DYNAMIC = {0: 1.0, 1: 2.0, 2: 3.0}


def panel(
    rng: np.random.Generator,
    n: int = 600,
    periods: int = 8,
    cohorts: tuple[int, ...] = (5,),
    dynamic: dict[int, float] | None = None,
    cohort_scale: tuple[float, ...] | None = None,
) -> pd.DataFrame:
    dynamic = DYNAMIC if dynamic is None else dynamic
    groups = rng.integers(0, len(cohorts) + 1, n)  # last group = never treated
    level = rng.normal(0, 2, n)
    time_fe = rng.normal(0, 1, periods + 1)
    rows = []
    for i in range(n):
        g = groups[i]
        start = float(cohorts[g]) if g < len(cohorts) else np.nan
        scale = cohort_scale[g] if cohort_scale and g < len(cohorts) else 1.0
        for t in range(1, periods + 1):
            k = t - start
            eff = scale * dynamic.get(int(k), dynamic[max(dynamic)]) if k >= 0 else 0.0
            rows.append(
                {
                    "unit_id": i,
                    "period": t,
                    "treatment_start": start,
                    "outcome": level[i] + time_fe[t] + eff + rng.normal(0, 0.5),
                }
            )
    return pd.DataFrame(rows)


def coef_map(result: object) -> dict[int, float]:
    return {c["relative_time"]: c["coef"] for c in result.metrics["coefficients"]}  # type: ignore[attr-defined]


def test_relative_time_indexing() -> None:
    df = pd.DataFrame({"period": [1, 2, 3, 4], "treatment_start": [3.0, 3.0, 3.0, np.nan]})
    rel = relative_time(df, SPEC)
    assert rel.iloc[:3].tolist() == [-2.0, -1.0, 0.0]
    assert np.isnan(rel.iloc[3])


def test_single_cohort_recovers_dynamic_path(rng: np.random.Generator) -> None:
    result = twfe_event_study(panel(rng), SPEC)
    coefs = coef_map(result)
    assert sorted(coefs) == [-4, -3, -2, -1, 0, 1, 2, 3]
    assert coefs[-1] == 0.0  # reference
    for k in (-4, -3, -2):
        assert coefs[k] == pytest.approx(0.0, abs=0.15)
    for k, effect in DYNAMIC.items():
        assert coefs[k] == pytest.approx(effect, abs=0.15)
    assert result.status is DiagnosticStatus.PASS
    assert "diagnostic baseline" in str(result.metrics["label"])


def test_window_bins_endpoints(rng: np.random.Generator) -> None:
    result = twfe_event_study(panel(rng), SPEC, window=(-2, 2))
    rows = {c["relative_time"]: c for c in result.metrics["coefficients"]}  # type: ignore[union-attr,index]
    assert sorted(rows) == [-2, -1, 0, 1, 2]
    assert rows[2]["binned_endpoint"] is True and rows[0]["binned_endpoint"] is False


def test_staggered_use_is_flagged(rng: np.random.Generator) -> None:
    data = panel(rng, cohorts=(3, 6), cohort_scale=(1.0, 3.0))
    result = twfe_event_study(data, SPEC)
    assert "twfe_event_study_staggered" in result.codes()
    assert result.metrics["staggered"] is True


def test_reference_must_be_observed_and_inside_window(rng: np.random.Generator) -> None:
    data = panel(rng, n=100)
    with pytest.raises(ValueError, match="inside the window"):
        twfe_event_study(data, SPEC, window=(0, 2))
    with pytest.raises(ValueError, match="not observed"):
        twfe_event_study(data, SPEC, reference=-20)


def test_unbalanced_panel_refused(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="balanced"):
        twfe_event_study(panel(rng, n=100).drop(index=5), SPEC)


def test_two_way_demean_matches_dummy_regression(rng: np.random.Generator) -> None:
    data = panel(rng, n=40)
    unit, period = data["unit_id"].to_numpy(), data["period"].to_numpy()
    d = (data["period"] >= data["treatment_start"]).to_numpy(dtype=float)
    y = data["outcome"].to_numpy()
    fit = ols_cluster_robust(
        two_way_demean(d, unit, period)[:, None], two_way_demean(y, unit, period), unit
    )
    dummies = pd.get_dummies(data[["unit_id", "period"]].astype(str), drop_first=True)
    full = np.column_stack([np.ones(len(d)), d, dummies.to_numpy(dtype=float)])
    beta, *_ = np.linalg.lstsq(full, y, rcond=None)
    assert fit.coef[0] == pytest.approx(beta[1])
