"""CSV + study-file runner (used by scripts/run_analysis.py and the Iran example)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from causalimpact.services import InterpretationStatus
from causalimpact.services.registry import rerun_bundle
from causalimpact.services.study_file import StudyFile, run_study
from tests.unit.panel.test_synthetic_control import panel

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
IRAN = ROOT / "examples" / "iran_sanctions"


def study(**overrides: object) -> StudyFile:
    body = json.loads((IRAN / "study.json").read_text(encoding="utf-8"))
    body.update(overrides)
    return StudyFile.model_validate(body)


def test_study_file_runs_and_bundle_reruns(rng: np.random.Generator, tmp_path: Path) -> None:
    data = panel(rng, own_sd=0.0, noise=0.1, effect=4.0)
    synthetic_run = {"estimator": {"kind": "synthetic_control", "placebo_period": 9}, "seed": 1}
    outcome = run_study(study(run=synthetic_run), data, tmp_path / "bundle")
    assert outcome.result is not None and outcome.result.estimate is not None
    assert outcome.result.estimate.estimate == pytest.approx(4.0, abs=0.3)
    assert outcome.bundle is not None and (outcome.bundle / "report.md").exists()
    assert rerun_bundle(outcome.bundle).reproduced


def test_unjustified_assumptions_are_reported_not_run(rng: np.random.Generator) -> None:
    outcome = run_study(study(assumption_justifications={}), panel(rng))
    assert outcome.result is None
    assert any("lacks a justification" in p for p in outcome.problems)


def test_reserved_design_fields_rejected() -> None:
    body = json.loads((IRAN / "study.json").read_text(encoding="utf-8"))
    body["design"]["estimand_id"] = "x"
    with pytest.raises(ValueError, match="study file"):
        run_study(StudyFile.model_validate(body), panel(np.random.default_rng(0)))


def test_iran_example_runs_and_is_not_overclaimed(tmp_path: Path) -> None:
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts/run_analysis.py"),
         "--data", str(IRAN / "inflation.csv"), "--study", str(IRAN / "study.json"),
         "--out", str(tmp_path / "iran")],
        capture_output=True, text=True, check=True,
    )  # fmt: skip
    assert InterpretationStatus.SUGGESTIVE.value in done.stdout
    assert InterpretationStatus.SUPPORTED.value not in done.stdout
    assert (tmp_path / "iran" / "report.md").exists()
