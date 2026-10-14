"""Task 6.1: happy-path and blocked-path integration tests for the analysis service."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.diagnostics import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain import DesignNotReadyError, DesignStatus, RunStatus
from causalimpact.services import DiagnosticStep, InterpretationStatus
from tests.integration.scenarios import observational, rct

pytestmark = pytest.mark.integration


def test_rct_happy_path(rng: np.random.Generator) -> None:
    s = rct(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=7)
    assert result.interpretation is InterpretationStatus.SUPPORTED
    assert result.estimate is not None
    assert abs(result.estimate.estimate - 0.3) < 4 * result.estimate.std_error
    assert result.run.status is RunStatus.COMPLETED
    assert result.run.estimand_id == "itt_revenue"
    assert result.run.dataset_version.startswith("sha256:")
    assert result.run_fingerprint == result.run.fingerprint
    assert result.required_diagnostics == ("attrition", "sample_ratio_mismatch")
    assert any("no_interference" in lim for lim in result.limitations)


def test_srm_blocks_and_withholds_estimate(rng: np.random.Generator) -> None:
    s = rct(rng, srm=True)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=7)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED
    assert result.estimate is None
    assert any("sample_ratio_mismatch" in r for r in result.reasons)
    assert any("fail-closed" in r for r in result.reasons)
    assert result.run.status is RunStatus.COMPLETED


def test_optional_blocking_diagnostic_makes_result_suggestive(rng: np.random.Generator) -> None:
    s = rct(rng)

    def noisy(_: object) -> DiagnosticResult:
        return DiagnosticResult(
            name="logging_completeness",
            findings=(Finding(code="gap", severity=FindingSeverity.WARNING, message="gap"),),
        )

    steps = [*s.diagnostics, DiagnosticStep("logging_completeness", noisy, required=False)]
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=steps, seed=7)
    assert result.interpretation is InterpretationStatus.SUGGESTIVE
    assert result.estimate is not None


def test_observational_happy_path(rng: np.random.Generator) -> None:
    s = observational(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    assert result.interpretation is InterpretationStatus.SUPPORTED
    assert result.estimate is not None
    assert abs(result.estimate.estimate - 2.0) < 4 * result.estimate.std_error
    assert result.run.dag_version == s.design.dag_version


def test_observational_poor_overlap_blocks(rng: np.random.Generator) -> None:
    s = observational(rng, strength=6.0)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED
    assert result.estimate is None


def test_estimator_failure_is_recorded_on_the_run(rng: np.random.Generator) -> None:
    s = rct(rng)
    broken = s.data.assign(revenue=s.data["revenue"].where(s.data.index != 0))
    result = s.service.run(s.design, s.estimator, broken, seed=7)
    assert result.run.status is RunStatus.FAILED
    assert "missing outcomes" in str(result.run.failure_reason)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED


def test_design_must_be_ready(rng: np.random.Generator) -> None:
    s = rct(rng)
    draft = s.design.transition(DesignStatus.DRAFT, reason="reopen")
    with pytest.raises(DesignNotReadyError):
        s.service.run(draft, s.estimator, s.data, seed=7)


def test_same_inputs_same_fingerprint(rng: np.random.Generator) -> None:
    s = rct(rng)
    a = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=7)
    b = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=7)
    assert a.run.run_id != b.run.run_id
    assert a.run_fingerprint == b.run_fingerprint
    assert a.estimate == b.estimate
