"""Task 7.6: injected failure modes are detected and labelled; controls stay quiet."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from causalimpact.simulation.failure_modes import FailureModeReport, run_failure_mode_suite

pytestmark = pytest.mark.simulation


@pytest.fixture(scope="module")
def report() -> FailureModeReport:
    return run_failure_mode_suite(seed=11, n_replicates=8)


@pytest.mark.parametrize(
    "name", ["srm", "differential_attrition", "pre_trend", "staggered_heterogeneity"]
)
def test_failure_modes_are_detected(report: FailureModeReport, name: str) -> None:
    scenario = report.scenario(name)
    assert scenario.failure_injected
    assert scenario.detection_rate is not None and scenario.detection_rate >= 0.9, scenario


@pytest.mark.parametrize(
    "name", ["srm_control", "attrition_control", "pre_trend_control", "single_cohort_control"]
)
def test_clean_controls_rarely_alarm(report: FailureModeReport, name: str) -> None:
    scenario = report.scenario(name)
    assert not scenario.failure_injected
    assert scenario.detection_rate is not None and scenario.detection_rate <= 0.25, scenario


def test_peeking_inflation_is_demonstrated_and_honestly_labelled(
    report: FailureModeReport,
) -> None:
    peeking = report.scenario("repeated_peeking")
    assert peeking.detection_rate is None
    assert "Task 2.12" in peeking.detector
    rate = float(peeking.note.split("false-positive rate ")[1].split(" ")[0])
    assert rate > 0.12  # well above the nominal 0.05


def test_report_is_a_ci_artifact(report: FailureModeReport, tmp_path: Path) -> None:
    path = report.write(tmp_path / "artifacts" / "failure_modes.json")
    body = json.loads(path.read_text())
    assert body["seed"] == 11
    assert len(body["scenarios"]) == 9
    assert FailureModeReport.model_validate_json(path.read_text()) == report
