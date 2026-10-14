"""Task 4.5: an injected pre-trend is detected; absence is never called proof."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticResult, DiagnosticStatus
from causalimpact.panel.event_study import twfe_event_study
from causalimpact.panel.pre_trends import check_pre_trends
from tests.unit.panel.test_event_study import SPEC, panel


def with_pre_trend(data: pd.DataFrame, slope: float) -> pd.DataFrame:
    """Treated units drift by ``slope`` per period relative to controls (all periods)."""
    treated = data["treatment_start"].notna()
    return data.assign(outcome=data["outcome"] + slope * data["period"] * treated)


def test_no_pre_trend_passes_with_caveat(rng: np.random.Generator) -> None:
    result = check_pre_trends(twfe_event_study(panel(rng), SPEC))
    assert result.status is DiagnosticStatus.PASS
    assert "does not prove parallel trends" in result.notes[0]
    assert result.metrics["pre_periods"] == [-4, -3, -2]
    assert result.metrics["joint_df"][0] == 3  # type: ignore[index]


def test_injected_pre_trend_blocks(rng: np.random.Generator) -> None:
    data = with_pre_trend(panel(rng), slope=0.3)
    result = check_pre_trends(twfe_event_study(data, SPEC))
    assert result.is_blocking
    assert "pre_trend_detected" in result.codes()
    assert result.metrics["linear_pre_trend_slope"] == pytest.approx(0.3, abs=0.08)


def test_wald_statistic_hand_check() -> None:
    es = DiagnosticResult(
        name="event_study_twfe",
        metrics={
            "reference_relative_time": -1,
            "coefficient_order": [-3, -2, 0],
            "covariance": [[0.04, 0.0, 0.0], [0.0, 0.01, 0.0], [0.0, 0.0, 1.0]],
            "n_clusters": 101,
            "coefficients": [
                {"relative_time": -3, "coef": 0.2},
                {"relative_time": -2, "coef": 0.1},
                {"relative_time": -1, "coef": 0.0},
                {"relative_time": 0, "coef": 5.0},
            ],
        },
    )
    result = check_pre_trends(es)
    # W = 0.2^2/0.04 + 0.1^2/0.01 = 2; F = W/2 = 1 on (2, 100) df
    assert result.metrics["joint_f_statistic"] == pytest.approx(1.0)
    assert result.metrics["joint_p_value"] == pytest.approx(0.3715, abs=1e-3)


def test_no_pre_periods_warns(rng: np.random.Generator) -> None:
    data = panel(rng, n=200)
    data = data[data["period"] >= 4]  # only relative time -1 remains before treatment
    result = check_pre_trends(twfe_event_study(data, SPEC))
    assert result.codes() == {"no_pre_period_coefficients"}


def test_wrong_input_rejected() -> None:
    with pytest.raises(ValueError, match="event-study"):
        check_pre_trends(DiagnosticResult(name="srm"))


@pytest.mark.simulation
def test_detection_power_and_size(rng: np.random.Generator) -> None:
    sims = 80
    null_rejections = sum(
        check_pre_trends(twfe_event_study(panel(rng, n=300), SPEC)).is_blocking for _ in range(sims)
    )
    trend_detections = sum(
        check_pre_trends(
            twfe_event_study(with_pre_trend(panel(rng, n=300), 0.15), SPEC)
        ).is_blocking
        for _ in range(sims)
    )
    assert null_rejections / sims <= 0.12
    assert trend_detections / sims >= 0.8
