"""AnalysisRun: one specification executed against one StudyDesign version.

A run pins the exact design version it was created from, so later design revisions never
silently change what a historical run meant. Runs are never overwritten: a run affected by
a bug is moved to Invalidated with a reason (RUNBOOK.md, "Result invalidation").

``run_id`` identifies one *execution*; ``fingerprint`` identifies the *specification*.
Two runs with identical design content, dataset, estimand, estimator, DAG/adjustment set,
learners, config, seed, confidence level and code version share a fingerprint, and any
change to those inputs changes it. Lifecycle fields (id, status, timestamps, reasons) are
excluded from the fingerprint.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from causalimpact.domain.errors import DesignNotReadyError, IllegalTransitionError
from causalimpact.domain.fingerprint import content_hash, derive_seed
from causalimpact.domain.ids import DesignId, RunId, new_run_id
from causalimpact.domain.study_design import StudyDesign
from causalimpact.domain.types import AwareDatetime, NonBlankStr, utc_now


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    INVALIDATED = "invalidated"


ALLOWED_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.PENDING: frozenset({RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset({RunStatus.COMPLETED, RunStatus.FAILED}),
    RunStatus.COMPLETED: frozenset({RunStatus.INVALIDATED}),
    RunStatus.FAILED: frozenset({RunStatus.INVALIDATED}),
    RunStatus.INVALIDATED: frozenset(),
}


# Execution/lifecycle fields excluded from the specification fingerprint.
RUN_FINGERPRINT_EXCLUDES = frozenset(
    {"run_id", "status", "created_at", "failure_reason", "invalidation_reason"}
)


class AnalysisRun(BaseModel):
    """Immutable record of a single analysis specification and its execution state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: RunId = Field(default_factory=new_run_id)
    design_id: DesignId
    design_version: int = Field(ge=1)
    design_content_hash: NonBlankStr
    status: RunStatus = RunStatus.PENDING
    created_at: AwareDatetime = Field(default_factory=utc_now)

    # Specification metadata (ARCHITECTURE.md, "AnalysisRun").
    estimand_id: NonBlankStr
    estimator: NonBlankStr
    dataset_version: NonBlankStr
    seed: int = Field(ge=0)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    dag_version: NonBlankStr | None = None
    adjustment_set_version: NonBlankStr | None = None
    nuisance_learners: dict[str, JsonValue] = Field(default_factory=dict)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    code_version: NonBlankStr | None = None

    failure_reason: NonBlankStr | None = None
    invalidation_reason: NonBlankStr | None = None

    @model_validator(mode="after")
    def _reasons_match_status(self) -> Self:
        if self.status is RunStatus.FAILED and self.failure_reason is None:
            raise ValueError("failed runs require a failure_reason")
        if self.failure_reason is not None and self.status not in {
            RunStatus.FAILED,
            RunStatus.INVALIDATED,
        }:
            raise ValueError("failure_reason is only allowed on failed or invalidated runs")
        if (self.status is RunStatus.INVALIDATED) != (self.invalidation_reason is not None):
            raise ValueError("invalidation_reason is required for, and only for, invalidated runs")
        return self

    @classmethod
    def for_design(cls, design: StudyDesign, **spec: Any) -> AnalysisRun:
        """Create a run pinned to ``design``'s current version.

        Fails closed if the design has not reached AnalysisReady, and refuses a run whose
        estimand differs from the design's: estimands are never switched silently.
        """
        if not design.is_analyzable:
            raise DesignNotReadyError(
                f"design {design.design_id} is {design.status}; runs require AnalysisReady"
            )
        estimand_id = spec.setdefault("estimand_id", design.estimand_id)
        if estimand_id != design.estimand_id:
            raise DesignNotReadyError(
                f"run estimand {estimand_id!r} does not match design estimand "
                f"{design.estimand_id!r}"
            )
        for key in ("dag_version", "adjustment_set_version"):
            value = spec.setdefault(key, getattr(design, key))
            if value != getattr(design, key):
                raise DesignNotReadyError(f"run {key} {value!r} does not match the design")
        return cls(
            design_id=design.design_id,
            design_version=design.version,
            design_content_hash=design.content_hash,
            **spec,
        )

    @property
    def fingerprint(self) -> str:
        """Stable identity of this run's specification (``sha256:<hex>``)."""
        spec = self.model_dump(mode="json", exclude=set(RUN_FINGERPRINT_EXCLUDES))
        return content_hash(spec)

    def derived_seed(self, purpose: str) -> int:
        """Deterministic child seed for one random step of this run."""
        return derive_seed(self.seed, purpose)

    def transition(self, to: RunStatus, *, reason: str | None = None) -> AnalysisRun:
        if to not in ALLOWED_RUN_TRANSITIONS[self.status]:
            raise IllegalTransitionError(f"cannot move run from {self.status} to {to}")
        update: dict[str, object] = {"status": to}
        if to is RunStatus.FAILED:
            update["failure_reason"] = reason
        if to is RunStatus.INVALIDATED:
            update["invalidation_reason"] = reason
        return AnalysisRun.model_validate({**self.model_dump(), **update})
