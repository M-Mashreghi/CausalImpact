"""Shared result type for diagnostics.

Diagnostics are independent of estimation and reporting: they return a structured
``DiagnosticResult`` that downstream layers must surface. A ``blocking`` finding means
the analysis cannot be reported as a trustworthy causal estimate until it is resolved.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

MAX_EXAMPLES = 5


class FindingSeverity(StrEnum):
    WARNING = "warning"
    BLOCKING = "blocking"


class DiagnosticStatus(StrEnum):
    PASS = "pass"
    WARNING = "warning"
    BLOCKING = "blocking"


class Finding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    severity: FindingSeverity
    message: str
    count: int = Field(default=1, ge=0)
    examples: tuple[str, ...] = ()


class DiagnosticResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    findings: tuple[Finding, ...] = ()
    metrics: dict[str, JsonValue] = Field(default_factory=dict)
    notes: tuple[str, ...] = ()

    @property
    def status(self) -> DiagnosticStatus:
        severities = {f.severity for f in self.findings}
        if FindingSeverity.BLOCKING in severities:
            return DiagnosticStatus.BLOCKING
        if FindingSeverity.WARNING in severities:
            return DiagnosticStatus.WARNING
        return DiagnosticStatus.PASS

    @property
    def is_blocking(self) -> bool:
        return self.status is DiagnosticStatus.BLOCKING

    def codes(self) -> set[str]:
        return {f.code for f in self.findings}

    def finding(self, code: str) -> Finding:
        for f in self.findings:
            if f.code == code:
                return f
        raise KeyError(code)


def examples(values: Iterable[object]) -> tuple[str, ...]:
    """Up to MAX_EXAMPLES sorted string examples from an iterable of ids."""
    items = sorted({str(v) for v in values})
    return tuple(items[:MAX_EXAMPLES])
