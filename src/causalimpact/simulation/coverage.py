"""Confidence-interval coverage benchmark and regression gate (Task 7.3).

Coverage is the share of replicates whose interval contains that replicate's truth,
reported with its Monte Carlo SE and the mean interval width. The gate fails when
coverage is severely below nominal (``nominal - max_shortfall``) or has dropped by more
than ``max_drop`` relative to a stored baseline; failures (refusals) are reported next
to coverage so that a method cannot look good by refusing hard cases.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.simulation.benchmark import BenchmarkResult


class CoverageSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case: str
    nominal: float
    n: int
    coverage: float
    coverage_mc_se: float
    mean_width: float
    failure_rate: float


class CoverageGate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_shortfall: float = Field(default=0.05, ge=0.0, lt=1.0)
    max_drop: float = Field(default=0.03, ge=0.0, lt=1.0)
    max_failure_rate: float = Field(default=0.05, ge=0.0, le=1.0)


def coverage_summary(result: BenchmarkResult, nominal: float = 0.95) -> CoverageSummary:
    if result.n_succeeded == 0:
        raise ValueError("no successful replicates; coverage is undefined")
    truths = np.array(result.truths)
    covered = (np.array(result.ci_lower) <= truths) & (truths <= np.array(result.ci_upper))
    cov = float(covered.mean())
    n = result.n_succeeded
    return CoverageSummary(
        case=result.case,
        nominal=nominal,
        n=n,
        coverage=cov,
        coverage_mc_se=math.sqrt(max(cov * (1 - cov), 1e-12) / n),
        mean_width=float(np.mean(np.array(result.ci_upper) - np.array(result.ci_lower))),
        failure_rate=result.failure_rate,
    )


def check_coverage(
    summary: CoverageSummary,
    gate: CoverageGate | None = None,
    baseline: CoverageSummary | None = None,
) -> DiagnosticResult:
    gate = gate or CoverageGate()
    findings: list[Finding] = []
    floor = summary.nominal - gate.max_shortfall
    if summary.coverage < floor:
        findings.append(
            Finding(
                code="severe_undercoverage",
                severity=FindingSeverity.BLOCKING,
                message=f"coverage {summary.coverage:.3f} < {floor:.3f} "
                f"(nominal {summary.nominal:.2f})",
            )
        )
    if baseline is not None and baseline.coverage - summary.coverage > gate.max_drop:
        findings.append(
            Finding(
                code="coverage_regression",
                severity=FindingSeverity.BLOCKING,
                message=f"coverage fell from {baseline.coverage:.3f} to {summary.coverage:.3f}",
            )
        )
    if summary.failure_rate > gate.max_failure_rate:
        findings.append(
            Finding(
                code="high_failure_rate",
                severity=FindingSeverity.BLOCKING,
                message=f"{summary.failure_rate:.1%} of replicates failed",
            )
        )
    return DiagnosticResult(
        name="coverage_gate",
        findings=tuple(findings),
        metrics={**summary.model_dump(), "gate": gate.model_dump()},
    )
