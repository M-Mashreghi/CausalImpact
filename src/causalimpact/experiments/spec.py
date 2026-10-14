"""Experiment metadata (DATA_CONTRACT.md, "Experiment metadata").

The unit randomized, the unit analysed, exposure logging and outcome logging are kept
explicitly distinct (DESIGN_PROTOCOL.md, "Experiment rule").
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalimpact.domain.types import NonBlankStr


class MonitoringPolicy(StrEnum):
    FIXED_HORIZON = "fixed_horizon"
    SEQUENTIAL = "sequential"


class Arm(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    allocation: float = Field(gt=0.0, lt=1.0)


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: NonBlankStr
    arms: tuple[Arm, ...]
    control_arm: NonBlankStr
    randomization_unit: NonBlankStr = Field(description="column holding the randomized unit id")
    analysis_unit: NonBlankStr = Field(description="column holding the analysed unit id")
    arm_column: NonBlankStr = "arm"
    assignment_time_column: NonBlankStr | None = None
    exposure_time_column: NonBlankStr | None = None
    primary_metric: NonBlankStr
    secondary_metrics: tuple[NonBlankStr, ...] = ()
    guardrail_metrics: tuple[NonBlankStr, ...] = ()
    planned_horizon: NonBlankStr | None = None
    monitoring_policy: MonitoringPolicy = MonitoringPolicy.FIXED_HORIZON

    @model_validator(mode="after")
    def _arms_consistent(self) -> Self:
        names = [a.name for a in self.arms]
        if len(names) < 2:
            raise ValueError("an experiment needs at least two arms")
        if len(set(names)) != len(names):
            raise ValueError("arm names must be unique")
        if self.control_arm not in names:
            raise ValueError(f"control arm {self.control_arm!r} is not one of the arms")
        total = sum(a.allocation for a in self.arms)
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError(f"arm allocations must sum to 1, got {total}")
        metrics = [self.primary_metric, *self.secondary_metrics, *self.guardrail_metrics]
        if len(set(metrics)) != len(metrics):
            raise ValueError("a metric can have only one role")
        return self

    @property
    def arm_names(self) -> tuple[str, ...]:
        return tuple(a.name for a in self.arms)

    @property
    def allocation(self) -> dict[str, float]:
        return {a.name: a.allocation for a in self.arms}

    @property
    def analysis_finer_than_randomization(self) -> bool:
        return self.analysis_unit != self.randomization_unit
