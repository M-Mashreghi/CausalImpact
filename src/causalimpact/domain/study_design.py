"""Canonical StudyDesign model and its lifecycle.

A StudyDesign captures *what* is being studied (question, population, treatment, outcome,
design family) independently of *how* it is estimated. One design can back many
AnalysisRuns with different specifications.

Lifecycle (DESIGN_PROTOCOL.md)::

    Draft -> Validated -> AnalysisReady -> Estimated -> Reviewed -> Reported

Revisions go back to Draft from Validated or AnalysisReady. Promotion to AnalysisReady
fails closed: it requires an explicit readiness check, and the default check refuses.
The structured identification checks are supplied by design validation (Task 1.6).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalimpact.domain.assumptions import Assumption
from causalimpact.domain.errors import DesignNotReadyError, IllegalTransitionError
from causalimpact.domain.ids import DesignId, new_design_id
from causalimpact.domain.types import AwareDatetime, NonBlankStr, utc_now


class DesignFamily(StrEnum):
    """Design family; selects which engine may estimate the design."""

    RANDOMIZED_EXPERIMENT = "randomized_experiment"
    OBSERVATIONAL = "observational"
    PANEL = "panel"


class DesignStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    ANALYSIS_READY = "analysis_ready"
    ESTIMATED = "estimated"
    REVIEWED = "reviewed"
    REPORTED = "reported"


ALLOWED_DESIGN_TRANSITIONS: dict[DesignStatus, frozenset[DesignStatus]] = {
    DesignStatus.DRAFT: frozenset({DesignStatus.VALIDATED}),
    DesignStatus.VALIDATED: frozenset({DesignStatus.ANALYSIS_READY, DesignStatus.DRAFT}),
    DesignStatus.ANALYSIS_READY: frozenset({DesignStatus.ESTIMATED, DesignStatus.DRAFT}),
    DesignStatus.ESTIMATED: frozenset({DesignStatus.REVIEWED}),
    DesignStatus.REVIEWED: frozenset({DesignStatus.REPORTED}),
    DesignStatus.REPORTED: frozenset(),
}

# Statuses at which a design may back an AnalysisRun.
ANALYZABLE_STATUSES: frozenset[DesignStatus] = frozenset(
    {
        DesignStatus.ANALYSIS_READY,
        DesignStatus.ESTIMATED,
        DesignStatus.REVIEWED,
        DesignStatus.REPORTED,
    }
)


class TargetPopulation(BaseModel):
    """The population the estimand refers to. Restrictions must be explicit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    description: NonBlankStr
    inclusion_criteria: tuple[NonBlankStr, ...] = ()
    exclusion_criteria: tuple[NonBlankStr, ...] = ()


class StatusChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    from_status: DesignStatus | None
    to_status: DesignStatus
    at: AwareDatetime
    reason: NonBlankStr


ReadinessCheck = Callable[["StudyDesign"], list[str]]
"""Returns a list of blocking problems; an empty list means the design is ready."""


def refuse_without_validator(design: StudyDesign) -> list[str]:
    """Default readiness check: fail closed until a real validator is supplied."""
    return ["no readiness validator configured; AnalysisReady fails closed"]


class StudyDesign(BaseModel):
    """Immutable, versioned study design record.

    Core fields are required at construction. Identification fields (estimand, DAG and
    adjustment-set versions, assignment mechanism, ...) are optional while drafting and
    are enforced by the readiness check on promotion to AnalysisReady.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    design_id: DesignId = Field(default_factory=new_design_id)
    version: int = Field(default=1, ge=1)
    status: DesignStatus = DesignStatus.DRAFT
    status_history: tuple[StatusChange, ...] = ()
    created_at: AwareDatetime = Field(default_factory=utc_now)

    # Core fields (required).
    title: NonBlankStr
    research_question: NonBlankStr
    design_family: DesignFamily
    target_population: TargetPopulation
    unit_of_analysis: NonBlankStr
    treatment: NonBlankStr
    outcome: NonBlankStr

    # Identification / planning fields (required for AnalysisReady, see Task 1.6).
    assignment_mechanism: NonBlankStr | None = None
    randomization_unit: NonBlankStr | None = None
    time_zero: NonBlankStr | None = None
    estimand_id: NonBlankStr | None = None
    dag_version: NonBlankStr | None = None
    adjustment_set_version: NonBlankStr | None = None
    forbidden_post_treatment_variables: tuple[NonBlankStr, ...] = ()
    interference_assessment: NonBlankStr | None = None
    missingness_plan: NonBlankStr | None = None
    overlap_expectations: NonBlankStr | None = None
    inference_unit: NonBlankStr | None = None
    cluster_variable: NonBlankStr | None = None
    sensitivity_plan: NonBlankStr | None = None
    primary_analysis: NonBlankStr | None = None
    secondary_analyses: tuple[NonBlankStr, ...] = ()
    assumptions: tuple[Assumption, ...] = ()

    @model_validator(mode="after")
    def _treatment_outcome_distinct(self) -> Self:
        if self.treatment == self.outcome:
            raise ValueError("treatment and outcome must be different variables")
        if self.treatment in self.forbidden_post_treatment_variables:
            raise ValueError("treatment cannot be listed as a post-treatment variable")
        keys = [a.key for a in self.assumptions]
        if len(keys) != len(set(keys)):
            raise ValueError("assumption keys must be unique")
        return self

    def transition(
        self,
        to: DesignStatus,
        *,
        reason: str,
        readiness_check: ReadinessCheck = refuse_without_validator,
        at: datetime | None = None,
    ) -> StudyDesign:
        """Return a new design in status ``to``; the original is unchanged."""
        if to not in ALLOWED_DESIGN_TRANSITIONS[self.status]:
            raise IllegalTransitionError(f"cannot move design from {self.status} to {to}")
        if to is DesignStatus.ANALYSIS_READY:
            problems = readiness_check(self)
            if problems:
                raise DesignNotReadyError("; ".join(problems))
        change = StatusChange(
            from_status=self.status, to_status=to, at=at or utc_now(), reason=reason
        )
        return self.model_copy(
            update={"status": to, "status_history": (*self.status_history, change)}
        )

    def revise(self, *, reason: str, at: datetime | None = None, **changes: object) -> StudyDesign:
        """Return a new Draft version with ``changes`` applied and re-validated.

        Editing is only possible in Draft; a design in Validated or AnalysisReady must be
        moved back to Draft first so that it is re-validated before analysis.
        """
        if self.status is not DesignStatus.DRAFT:
            raise IllegalTransitionError(f"only Draft designs can be revised, not {self.status}")
        protected = {"design_id", "version", "status", "status_history", "created_at"}
        if bad := protected & changes.keys():
            raise IllegalTransitionError(f"fields are not revisable: {sorted(bad)}")
        data = self.model_dump()
        data.update(changes)
        data["version"] = self.version + 1
        data["status_history"] = (
            *self.status_history,
            StatusChange(
                from_status=self.status,
                to_status=DesignStatus.DRAFT,
                at=at or utc_now(),
                reason=reason,
            ),
        )
        return StudyDesign.model_validate(data)

    @property
    def is_analyzable(self) -> bool:
        return self.status in ANALYZABLE_STATUSES
