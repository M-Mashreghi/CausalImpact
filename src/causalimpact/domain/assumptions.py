"""Structured identification assumptions (CAUSAL_ASSUMPTIONS.md).

An assumption is recorded as an assumption. Its status can say that diagnostics support or
raise concerns about it, but never that it has been proven: a model running successfully
does not turn an identifying assumption into a fact.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from causalimpact.domain.types import NonBlankStr


class Testability(StrEnum):
    UNTESTABLE = "untestable"
    PARTIALLY_TESTABLE = "partially_testable"
    TESTABLE = "testable"


class AssumptionStatus(StrEnum):
    ASSUMED = "assumed"
    DIAGNOSTIC_SUPPORT = "diagnostic_support"
    DIAGNOSTIC_CONCERN = "diagnostic_concern"
    VIOLATED = "violated"


class Assumption(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: NonBlankStr
    statement: NonBlankStr
    testability: Testability
    status: AssumptionStatus = AssumptionStatus.ASSUMED
    justification: NonBlankStr | None = None
    related_diagnostics: tuple[NonBlankStr, ...] = ()

    def justify(self, justification: str) -> Assumption:
        return self.model_copy(update={"justification": justification})
