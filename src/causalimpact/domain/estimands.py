"""Estimand registry and the estimand contract for estimator outputs.

The estimand is fixed before an estimator is chosen (CLAUDE.md, "Estimand first"). Every
estimator output must declare which registered estimand it targets, and
``check_estimate_targets`` refuses outputs whose declared estimand differs from the one
the analysis was designed for: an estimand is never switched silently.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter, model_validator

from causalimpact.domain.errors import DomainError
from causalimpact.domain.study_design import TargetPopulation
from causalimpact.domain.types import NonBlankStr


class EstimandType(StrEnum):
    ATE = "ATE"
    ATT = "ATT"
    ATC = "ATC"
    CATE = "CATE"
    ITT = "ITT"


class TreatmentBasis(StrEnum):
    """Whether contrasts are defined on treatment *assignment* or treatment *receipt*."""

    ASSIGNMENT = "assignment"
    RECEIPT = "receipt"


class EffectScale(StrEnum):
    DIFFERENCE = "difference"
    RATIO = "ratio"


# Which units the average is taken over, relative to the declared target population.
ESTIMAND_SUBPOPULATION: dict[EstimandType, str] = {
    EstimandType.ATE: "all units in the target population",
    EstimandType.ATT: "treated units in the target population",
    EstimandType.ATC: "untreated (control) units in the target population",
    EstimandType.CATE: "units in the target population sharing the conditioning values",
    EstimandType.ITT: "all units assigned in the target population, analysed as assigned",
}


class EstimandMismatchError(DomainError):
    """An estimator output does not target the estimand the analysis requires."""


class Estimand(BaseModel):
    """A fully specified causal target: contrast, population, treatment, outcome, scale."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    estimand_id: NonBlankStr
    type: EstimandType
    treatment: NonBlankStr
    outcome: NonBlankStr
    target_population: TargetPopulation
    treatment_basis: TreatmentBasis = TreatmentBasis.RECEIPT
    scale: EffectScale = EffectScale.DIFFERENCE
    conditioning_variables: tuple[NonBlankStr, ...] = ()
    description: NonBlankStr | None = None

    @model_validator(mode="after")
    def _type_rules(self) -> Self:
        if self.type is EstimandType.CATE and not self.conditioning_variables:
            raise ValueError("CATE requires at least one conditioning variable")
        if self.type is not EstimandType.CATE and self.conditioning_variables:
            raise ValueError(f"{self.type} does not take conditioning variables")
        if self.type is EstimandType.ITT and self.treatment_basis is not TreatmentBasis.ASSIGNMENT:
            raise ValueError("ITT is defined on treatment assignment (treatment_basis=assignment)")
        if self.treatment in self.conditioning_variables:
            raise ValueError("the treatment cannot be a conditioning variable")
        if self.outcome in self.conditioning_variables:
            raise ValueError("the outcome cannot be a conditioning variable")
        return self

    @property
    def averaged_over(self) -> str:
        return ESTIMAND_SUBPOPULATION[self.type]


class EffectEstimate(BaseModel):
    """Output contract every estimator returns. It must name the estimand it targets."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    estimand_id: NonBlankStr
    estimand_type: EstimandType
    estimator: NonBlankStr
    estimate: float
    std_error: float = Field(ge=0.0)
    ci_lower: float
    ci_upper: float
    confidence_level: float = Field(gt=0.0, lt=1.0)
    inference_method: NonBlankStr
    p_value: float | None = Field(default=None, ge=0.0, le=1.0)
    degrees_of_freedom: float | None = Field(default=None, gt=0.0)
    n_units: int = Field(ge=1)
    n_treated: int | None = Field(default=None, ge=0)
    n_control: int | None = Field(default=None, ge=0)
    conditioning_values: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _numerically_sane(self) -> Self:
        values = (self.estimate, self.std_error, self.ci_lower, self.ci_upper)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("estimate, std_error and CI bounds must be finite")
        if not self.ci_lower <= self.estimate <= self.ci_upper:
            raise ValueError("estimate must lie within [ci_lower, ci_upper]")
        arms = (self.n_treated, self.n_control)
        if None not in arms and sum(a for a in arms if a is not None) > self.n_units:
            raise ValueError("n_treated + n_control exceeds n_units")
        return self


def check_estimate_targets(estimand: Estimand, output: EffectEstimate) -> EffectEstimate:
    """Return ``output`` if it targets ``estimand``; raise EstimandMismatchError otherwise."""
    problems: list[str] = []
    if output.estimand_id != estimand.estimand_id:
        problems.append(
            f"output targets estimand {output.estimand_id!r}, expected {estimand.estimand_id!r}"
        )
    if output.estimand_type is not estimand.type:
        problems.append(f"output estimand type {output.estimand_type} != {estimand.type}")
    if estimand.type is EstimandType.CATE:
        expected = set(estimand.conditioning_variables)
        if set(output.conditioning_values) != expected:
            problems.append(f"CATE output must condition on exactly {sorted(expected)}")
    elif output.conditioning_values:
        problems.append(f"{estimand.type} output must not carry conditioning values")
    if problems:
        raise EstimandMismatchError("; ".join(problems))
    return output


_ESTIMAND_LIST = TypeAdapter(list[Estimand])


class EstimandRegistry:
    """In-memory registry of estimands keyed by id.

    Registered estimands are immutable: re-registering an identical estimand is a no-op,
    and registering different content under an existing id is refused.
    """

    def __init__(self, estimands: tuple[Estimand, ...] | list[Estimand] = ()) -> None:
        self._items: dict[str, Estimand] = {}
        for estimand in estimands:
            self.register(estimand)

    def register(self, estimand: Estimand) -> Estimand:
        existing = self._items.get(estimand.estimand_id)
        if existing is not None and existing != estimand:
            raise DomainError(
                f"estimand {estimand.estimand_id!r} is already registered with different "
                "content; register a new id instead of redefining it"
            )
        self._items[estimand.estimand_id] = estimand
        return estimand

    def get(self, estimand_id: str) -> Estimand:
        try:
            return self._items[estimand_id]
        except KeyError:
            raise DomainError(f"unknown estimand {estimand_id!r}") from None

    def __contains__(self, estimand_id: object) -> bool:
        return estimand_id in self._items

    def __iter__(self) -> Iterator[Estimand]:
        return iter(sorted(self._items.values(), key=lambda e: e.estimand_id))

    def __len__(self) -> int:
        return len(self._items)

    def to_json(self) -> str:
        return _ESTIMAND_LIST.dump_json(list(self)).decode()

    @classmethod
    def from_json(cls, payload: str | bytes) -> EstimandRegistry:
        return cls(_ESTIMAND_LIST.validate_json(payload))
