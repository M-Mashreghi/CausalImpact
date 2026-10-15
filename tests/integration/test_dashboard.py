"""Task 6.4: dashboard data adapters are tested and traceable to the run id."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from causalimpact.dashboard.adapters import (
    balance_frame,
    diagnostic_summary_frame,
    event_study_frame,
    overlap_frame,
    specification_frame,
    srm_frame,
    weights_frame,
)
from causalimpact.diagnostics import DiagnosticResult
from causalimpact.domain import EstimandType
from causalimpact.estimators import run_estimator
from causalimpact.experiments.balance import check_baseline_balance
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.event_study import twfe_event_study
from causalimpact.sensitivity.specification import (
    SpecificationGrid,
    SpecificationVariant,
    run_specifications,
)
from tests.integration.scenarios import X, observational, rct
from tests.unit.experiments.test_balance import COVS, FIXTURE, SPEC
from tests.unit.observational.test_weighting import TREATMENT, dgp, estimand
from tests.unit.panel.test_event_study import panel

pytestmark = pytest.mark.integration
APP = Path(__file__).resolve().parents[2] / "src/causalimpact/dashboard/diagnostics_app.py"


def test_summary_and_srm_frames(rng: np.random.Generator) -> None:
    s = rct(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    summary = diagnostic_summary_frame(result)
    assert set(summary["diagnostic"]) == {"sample_ratio_mismatch", "attrition"}
    assert (summary["run_id"] == result.run.run_id).all()
    srm = srm_frame(result.diagnostics[0], result.run.run_id)
    assert list(srm["arm"]) == ["control", "treatment"]
    assert srm["observed"].sum() == len(s.data)
    assert srm["configured_share"].tolist() == [0.5, 0.5]


def test_overlap_frame_preserves_histogram(rng: np.random.Generator) -> None:
    s = observational(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    frame = overlap_frame(result.diagnostics[0], "run_x")
    assert set(frame["arm"]) == {"treated", "control"}
    assert frame.groupby("arm")["count"].sum().sum() == len(s.data)
    assert (frame["bin_right"] > frame["bin_left"]).all()


def test_balance_frame_from_baseline_balance() -> None:
    frame = balance_frame(check_baseline_balance(SPEC, FIXTURE, COVS), "run_b")
    row = frame[(frame.covariate == "age")].iloc[0]
    assert row["smd"] == pytest.approx(-1.0392305)
    assert row["abs_smd"] == pytest.approx(1.0392305)
    assert (frame["run_id"] == "run_b").all()


def test_event_study_frame(rng: np.random.Generator) -> None:
    frame = event_study_frame(twfe_event_study(panel(rng), PanelSpec()), "run_e")
    assert frame["relative_time"].is_monotonic_increasing
    assert frame.loc[frame.reference, "coef"].tolist() == [0.0]
    assert "diagnostic baseline" in frame["label"].iloc[0]


def test_weights_and_specification_frames(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=800)
    est = WeightingEstimator(TREATMENT, (X,), WeightScheme.IPW, seed=1, n_bootstrap=50)
    out = run_estimator(est, data, estimand(EstimandType.ATE))
    weights = weights_frame(dict(out.details), "run_w")
    assert list(weights["arm"]) == ["treated", "control"]
    grid = SpecificationGrid(
        (SpecificationVariant("ipw", est),),
        primary="ipw",
        declared_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    report = run_specifications(
        grid, data, estimand(EstimandType.ATE), run_at=datetime(2026, 2, 1, tzinfo=UTC)
    )
    spec = specification_frame(report, "run_w")
    assert spec.loc[0, "status"] == "succeeded" and spec.loc[0, "grid_fingerprint"]


def test_adapters_reject_wrong_diagnostics() -> None:
    with pytest.raises(ValueError, match="expected a 'overlap'"):
        overlap_frame(DiagnosticResult(name="srm"), "r")
    with pytest.raises(ValueError, match="no balance table"):
        balance_frame(DiagnosticResult(name="x"), "r")


def test_dashboard_smoke(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    path = tmp_path / "result.json"
    path.write_text(result.model_dump_json(), encoding="utf-8")
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    at.text_input(key="result_path").input(str(path)).run()
    assert not at.exception
    assert any(result.run.run_id in c.value for c in at.caption)
    assert at.subheader[0].value == result.interpretation.value


def test_dashboard_accepts_bundle_folder_and_quoted_paths(
    rng: np.random.Generator, tmp_path: Path
) -> None:
    s = rct(rng, n=300)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    (tmp_path / "result.json").write_text(result.model_dump_json(), encoding="utf-8")
    for entered in (str(tmp_path), f'"{tmp_path}"', f'"{tmp_path / "result.json"}"'):
        at = AppTest.from_file(str(APP), default_timeout=60).run()
        at.text_input(key="result_path").input(entered).run()
        assert not at.exception and not at.error, entered
        assert at.subheader[0].value == result.interpretation.value
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    at.text_input(key="result_path").input(str(tmp_path / "missing")).run()
    assert "No analysis result found" in at.error[0].value
