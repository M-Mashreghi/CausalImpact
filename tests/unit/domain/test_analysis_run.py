"""Task 1.2: AnalysisRun is separate from, and pinned to, a StudyDesign version."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from causalimpact.domain import (
    ALLOWED_RUN_TRANSITIONS,
    AnalysisRun,
    DesignNotReadyError,
    DesignStatus,
    IllegalTransitionError,
    RunStatus,
    StudyDesign,
)
from tests.unit.domain.test_study_design import advance_to, make_design

SPEC: dict[str, Any] = {
    "estimator": "difference_in_means",
    "dataset_version": "sha256:abc",
    "seed": 7,
}


@pytest.fixture
def ready_design() -> StudyDesign:
    return advance_to(make_design(dag_version="dag_v1"), DesignStatus.ANALYSIS_READY)


def test_run_pins_design_version_and_inherits_identification(ready_design: StudyDesign) -> None:
    run = AnalysisRun.for_design(ready_design, **SPEC)
    assert run.design_id == ready_design.design_id
    assert run.design_version == ready_design.version
    assert run.estimand_id == ready_design.estimand_id
    assert run.dag_version == "dag_v1"
    assert run.status is RunStatus.PENDING
    assert run.run_id.startswith("run_")


def test_one_design_supports_many_specifications(ready_design: StudyDesign) -> None:
    a = AnalysisRun.for_design(ready_design, **SPEC)
    b = AnalysisRun.for_design(ready_design, **{**SPEC, "estimator": "regression_adjusted"})
    assert a.design_id == b.design_id
    assert a.run_id != b.run_id


@pytest.mark.parametrize("status", [DesignStatus.DRAFT, DesignStatus.VALIDATED])
def test_run_requires_analysis_ready_design(status: DesignStatus) -> None:
    design = advance_to(make_design(), status)
    with pytest.raises(DesignNotReadyError, match="AnalysisReady"):
        AnalysisRun.for_design(design, **SPEC)


def test_run_cannot_switch_estimand(ready_design: StudyDesign) -> None:
    with pytest.raises(DesignNotReadyError, match="estimand"):
        AnalysisRun.for_design(ready_design, estimand_id="ate_conversion", **SPEC)


def test_run_cannot_switch_dag(ready_design: StudyDesign) -> None:
    with pytest.raises(DesignNotReadyError, match="dag_version"):
        AnalysisRun.for_design(ready_design, dag_version="dag_v2", **SPEC)


@pytest.mark.parametrize("missing", ["estimator", "dataset_version", "seed"])
def test_missing_run_metadata_fails(ready_design: StudyDesign, missing: str) -> None:
    spec = {k: v for k, v in SPEC.items() if k != missing}
    with pytest.raises(ValidationError, match=missing):
        AnalysisRun.for_design(ready_design, **spec)


@pytest.mark.parametrize("level", [0.0, 1.0, 1.5])
def test_invalid_confidence_level_fails(ready_design: StudyDesign, level: float) -> None:
    with pytest.raises(ValidationError):
        AnalysisRun.for_design(ready_design, confidence_level=level, **SPEC)


def test_run_lifecycle_and_invalidation(ready_design: StudyDesign) -> None:
    run = AnalysisRun.for_design(ready_design, **SPEC)
    done = run.transition(RunStatus.RUNNING).transition(RunStatus.COMPLETED)
    invalid = done.transition(RunStatus.INVALIDATED, reason="bug in SE formula")
    assert invalid.invalidation_reason == "bug in SE formula"
    assert done.status is RunStatus.COMPLETED  # history is never overwritten
    assert invalid.run_id == run.run_id


def test_failed_run_requires_reason(ready_design: StudyDesign) -> None:
    run = AnalysisRun.for_design(ready_design, **SPEC).transition(RunStatus.RUNNING)
    with pytest.raises(ValidationError, match="failure_reason"):
        run.transition(RunStatus.FAILED)
    failed = run.transition(RunStatus.FAILED, reason="singular design matrix")
    assert failed.transition(RunStatus.INVALIDATED, reason="bad data").failure_reason


def test_invalidation_requires_reason(ready_design: StudyDesign) -> None:
    run = AnalysisRun.for_design(ready_design, **SPEC)
    done = run.transition(RunStatus.RUNNING).transition(RunStatus.COMPLETED)
    with pytest.raises(ValidationError, match="invalidation_reason"):
        done.transition(RunStatus.INVALIDATED)


@pytest.mark.parametrize(
    ("source", "target"),
    [(s, t) for s in RunStatus for t in RunStatus if t not in ALLOWED_RUN_TRANSITIONS[s]],
)
def test_illegal_run_transitions_fail(
    ready_design: StudyDesign, source: RunStatus, target: RunStatus
) -> None:
    run = AnalysisRun.for_design(ready_design, **SPEC)
    path = {
        RunStatus.PENDING: [],
        RunStatus.RUNNING: [(RunStatus.RUNNING, None)],
        RunStatus.COMPLETED: [(RunStatus.RUNNING, None), (RunStatus.COMPLETED, None)],
        RunStatus.FAILED: [(RunStatus.FAILED, "x")],
        RunStatus.INVALIDATED: [(RunStatus.FAILED, "x"), (RunStatus.INVALIDATED, "y")],
    }[source]
    for status, reason in path:
        run = run.transition(status, reason=reason)
    with pytest.raises(IllegalTransitionError):
        run.transition(target, reason="r")


def test_run_serialization_round_trip(ready_design: StudyDesign) -> None:
    run = AnalysisRun.for_design(
        ready_design, nuisance_learners={"propensity": {"model": "logit"}}, **SPEC
    )
    assert AnalysisRun.model_validate_json(run.model_dump_json()) == run
