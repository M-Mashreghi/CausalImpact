"""Core causal analysis service (Task 6.1).

Orchestrates, in this order and with no shortcuts:

1. design validation (the design must be AnalysisReady *and* still pass readiness);
2. estimand resolution from the registry (the design's estimand, never another);
3. dataset versioning and a pinned ``AnalysisRun``;
4. trust diagnostics: if any *required* diagnostic is blocking, estimation is withheld
   (fail closed) and the interpretation is "not supported";
5. estimation through ``run_estimator`` (estimand contract enforced);
6. an ``AnalysisResult`` artifact with interpretation status, assumptions, diagnostics
   and provenance, from which reports are rendered (Task 6.6).

The API and dashboard call this service; they contain no causal computation.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd
from pydantic import BaseModel, ConfigDict

import causalimpact
from causalimpact.dags import DagRegistry
from causalimpact.design.readiness import DesignReadinessValidator
from causalimpact.diagnostics.base import DiagnosticResult, DiagnosticStatus
from causalimpact.domain.analysis_run import AnalysisRun, RunStatus
from causalimpact.domain.assumptions import Assumption, AssumptionStatus, Testability
from causalimpact.domain.errors import DesignNotReadyError
from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandRegistry
from causalimpact.domain.study_design import StudyDesign
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.ingestion.dataset_version import dataset_version


class InterpretationStatus(StrEnum):
    """The three permitted interpretation labels (REPORTING_STANDARD.md)."""

    SUPPORTED = "Causal estimate supported under stated assumptions"
    SUGGESTIVE = "Suggestive; important diagnostics/assumptions unresolved"
    NOT_SUPPORTED = "Causal interpretation not supported"


@dataclass(frozen=True)
class DiagnosticStep:
    """A named diagnostic run on the analysis data before estimation."""

    name: str
    check: Callable[[pd.DataFrame], DiagnosticResult]
    required: bool = True


class AnalysisResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run: AnalysisRun
    run_fingerprint: str
    design: StudyDesign
    estimand: Estimand
    estimate: EffectEstimate | None
    diagnostics: tuple[DiagnosticResult, ...]
    required_diagnostics: tuple[str, ...]
    interpretation: InterpretationStatus
    reasons: tuple[str, ...]
    assumptions: tuple[Assumption, ...]
    limitations: tuple[str, ...]
    n_rows: int


def interpret(
    diagnostics: Sequence[DiagnosticResult],
    required: set[str],
    assumptions: Sequence[Assumption],
    estimate: EffectEstimate | None,
) -> tuple[InterpretationStatus, list[str]]:
    reasons: list[str] = []
    blocking = [d for d in diagnostics if d.is_blocking and d.name in required]
    for d in blocking:
        reasons.append(f"required diagnostic '{d.name}' is blocking: {sorted(d.codes())}")
    if blocking or estimate is None:
        if estimate is None and not blocking:
            reasons.append("no estimate was produced")
        return InterpretationStatus.NOT_SUPPORTED, reasons
    for d in diagnostics:
        if d.status is DiagnosticStatus.BLOCKING:
            reasons.append(f"optional diagnostic '{d.name}' is blocking")
        elif d.status is DiagnosticStatus.WARNING:
            reasons.append(f"diagnostic '{d.name}' raised warnings: {sorted(d.codes())}")
    for a in assumptions:
        if a.status is AssumptionStatus.DIAGNOSTIC_CONCERN:
            reasons.append(f"assumption '{a.key}' has a diagnostic concern")
    if reasons:
        return InterpretationStatus.SUGGESTIVE, reasons
    return InterpretationStatus.SUPPORTED, ["all required diagnostics passed"]


@dataclass(frozen=True)
class AnalysisService:
    estimands: EstimandRegistry
    dags: DagRegistry

    def run(
        self,
        design: StudyDesign,
        estimator: Estimator,
        data: pd.DataFrame,
        *,
        diagnostics: Sequence[DiagnosticStep] = (),
        seed: int,
        confidence_level: float = 0.95,
    ) -> AnalysisResult:
        problems = DesignReadinessValidator(self.estimands, self.dags)(design)
        if problems:
            raise DesignNotReadyError("; ".join(problems))
        assert design.estimand_id is not None  # guaranteed by readiness
        estimand = self.estimands.get(design.estimand_id)
        names = [d.name for d in diagnostics]
        if len(names) != len(set(names)):
            raise ValueError("diagnostic step names must be unique")

        run = AnalysisRun.for_design(
            design,
            estimator=estimator.name,
            dataset_version=dataset_version(data).content_hash,
            seed=seed,
            confidence_level=confidence_level,
            config={"estimator_definition": repr(estimator), "diagnostics": names},
            code_version=causalimpact.__version__,
        ).transition(RunStatus.RUNNING)

        results = tuple(step.check(data) for step in diagnostics)
        required = {d.name for d in diagnostics if d.required}
        by_step = dict(zip(names, results, strict=True))
        blocked = [n for n in required if by_step[n].is_blocking]

        estimate: EffectEstimate | None = None
        failure: str | None = None
        if not blocked:
            try:
                estimate = run_estimator(
                    estimator, data, estimand, confidence_level=confidence_level
                )
            except Exception as exc:  # recorded on the run, never swallowed silently
                failure = f"{type(exc).__name__}: {exc}"

        status, reasons = interpret(results, required, design.assumptions, estimate)
        if failure is not None:
            run = run.transition(RunStatus.FAILED, reason=failure)
            reasons.append(f"estimation failed: {failure}")
        else:
            run = run.transition(RunStatus.COMPLETED)
        if blocked:
            reasons.append("estimation withheld: fail-closed on blocking required diagnostics")

        limitations = [
            f"untestable assumption: {a.key} ({a.statement})"
            for a in design.assumptions
            if a.testability is Testability.UNTESTABLE
        ]
        return AnalysisResult(
            run=run,
            run_fingerprint=run.fingerprint,
            design=design,
            estimand=estimand,
            estimate=estimate,
            diagnostics=results,
            required_diagnostics=tuple(sorted(required)),
            interpretation=status,
            reasons=tuple(reasons),
            assumptions=design.assumptions,
            limitations=tuple(limitations),
            n_rows=len(data),
        )
