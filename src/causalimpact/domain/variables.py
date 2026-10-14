"""Treatment, outcome and covariate contracts (DATA_CONTRACT.md).

Covariates carry temporal metadata. Metadata alone decides whether a covariate may enter
an *automatic* adjustment set:

* a known descendant of treatment, or a variable measured after treatment, is forbidden;
* a variable with unknown timing or unknown descendant status needs researcher review and
  is never included automatically;
* only variables known to be pre-treatment and not affected by treatment are eligible.

DAG-based checks (mediators, colliders) are layered on top of this in Tasks 1.5 and 3.1.
Eligibility is necessary, not sufficient, for a variable to belong in an adjustment set.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from causalimpact.domain.study_design import NonBlankStr


class TriState(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class TreatmentKind(StrEnum):
    BINARY = "binary"


class OutcomeKind(StrEnum):
    CONTINUOUS = "continuous"
    BINARY = "binary"
    COUNT = "count"


class CovariateDType(StrEnum):
    NUMERIC = "numeric"
    BINARY = "binary"
    CATEGORICAL = "categorical"


class MissingnessPolicy(StrEnum):
    FORBID = "forbid"
    COMPLETE_CASE = "complete_case"
    INDICATOR = "indicator"
    IMPUTE_DECLARED = "impute_declared"


class TreatmentSpec(BaseModel):
    """A binary treatment column with explicit control and treated values."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    kind: TreatmentKind = TreatmentKind.BINARY
    control_value: int | str = 0
    treated_value: int | str = 1
    description: NonBlankStr | None = None

    @model_validator(mode="after")
    def _distinct_levels(self) -> Self:
        if self.control_value == self.treated_value:
            raise ValueError("control_value and treated_value must differ")
        return self


class OutcomeSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    kind: OutcomeKind
    measurement_time: NonBlankStr
    units: NonBlankStr | None = None
    description: NonBlankStr | None = None


class CovariateSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    dtype: CovariateDType
    measurement_time: NonBlankStr | None = None
    pre_treatment: TriState = TriState.UNKNOWN
    descendant_of_treatment: TriState = TriState.UNKNOWN
    missingness_policy: MissingnessPolicy = MissingnessPolicy.FORBID
    source: NonBlankStr | None = None

    @model_validator(mode="after")
    def _consistent_timing(self) -> Self:
        if self.pre_treatment is TriState.TRUE and self.descendant_of_treatment is TriState.TRUE:
            raise ValueError(
                f"{self.name}: a pre-treatment variable cannot be a descendant of treatment"
            )
        if self.pre_treatment is TriState.TRUE and self.measurement_time is None:
            raise ValueError(f"{self.name}: pre_treatment=true requires a measurement_time")
        return self


class Eligibility(StrEnum):
    ELIGIBLE = "eligible"
    REVIEW_REQUIRED = "review_required"
    FORBIDDEN = "forbidden"


class EligibilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    covariate: str
    eligibility: Eligibility
    reasons: tuple[str, ...]


def classify_covariate(covariate: CovariateSpec) -> EligibilityDecision:
    """Classify one covariate for automatic adjustment using its temporal metadata."""
    forbidden: list[str] = []
    review: list[str] = []
    if covariate.descendant_of_treatment is TriState.TRUE:
        forbidden.append("known descendant of treatment")
    if covariate.pre_treatment is TriState.FALSE:
        forbidden.append("measured after treatment")
    if covariate.pre_treatment is TriState.UNKNOWN:
        review.append("unknown measurement timing relative to treatment")
    if covariate.descendant_of_treatment is TriState.UNKNOWN:
        review.append("unknown whether affected by treatment")
    if forbidden:
        return EligibilityDecision(
            covariate=covariate.name, eligibility=Eligibility.FORBIDDEN, reasons=tuple(forbidden)
        )
    if review:
        return EligibilityDecision(
            covariate=covariate.name,
            eligibility=Eligibility.REVIEW_REQUIRED,
            reasons=tuple(review),
        )
    return EligibilityDecision(
        covariate=covariate.name,
        eligibility=Eligibility.ELIGIBLE,
        reasons=("known pre-treatment and not affected by treatment",),
    )


class DataContract(BaseModel):
    """Column-level contract for a unit-level analysis dataset."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    unit_id: NonBlankStr = "unit_id"
    treatment: TreatmentSpec
    outcome: OutcomeSpec
    covariates: tuple[CovariateSpec, ...] = ()
    timestamp: NonBlankStr | None = None
    cluster_id: NonBlankStr | None = None
    stratum: NonBlankStr | None = None
    sample_weight: NonBlankStr | None = None

    @model_validator(mode="after")
    def _unique_roles(self) -> Self:
        names = [
            self.unit_id,
            self.treatment.name,
            self.outcome.name,
            *(c.name for c in self.covariates),
        ]
        names += [n for n in (self.timestamp, self.sample_weight) if n is not None]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        if duplicates:
            raise ValueError(f"columns used in more than one role: {duplicates}")
        # cluster_id / stratum may legitimately reuse a covariate column, but never the
        # treatment or outcome.
        for role in (self.cluster_id, self.stratum):
            if role in {self.treatment.name, self.outcome.name}:
                raise ValueError(f"{role!r} cannot be both a design column and treatment/outcome")
        return self

    def covariate(self, name: str) -> CovariateSpec:
        for c in self.covariates:
            if c.name == name:
                return c
        raise KeyError(name)

    def screen_covariates(self) -> dict[Eligibility, tuple[EligibilityDecision, ...]]:
        """Group every declared covariate by its automatic-adjustment eligibility."""
        decisions = [classify_covariate(c) for c in self.covariates]
        return {
            level: tuple(d for d in decisions if d.eligibility is level) for level in Eligibility
        }

    def automatic_adjustment_candidates(self) -> tuple[str, ...]:
        """Names of covariates that may enter an adjustment set without review."""
        return tuple(d.covariate for d in self.screen_covariates()[Eligibility.ELIGIBLE])
