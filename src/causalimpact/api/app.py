"""FastAPI study and analysis API (Task 6.2).

Thin HTTP layer over the services: it validates typed requests, calls the registries
and ``AnalysisService``, and serialises results. It performs no causal computation.

Errors are mapped to typed JSON bodies. Domain violations become 409/422 with the
violation message; unexpected exceptions become a generic 500 with an opaque error id.
Stack traces, settings and environment values are never returned.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from causalimpact.dags import AdjustmentSet, CausalDAG, DagRegistry
from causalimpact.design import DesignReadinessValidator
from causalimpact.diagnostics import DiagnosticResult
from causalimpact.domain import (
    DesignNotReadyError,
    DesignStatus,
    DomainError,
    Estimand,
    EstimandRegistry,
    StudyDesign,
)
from causalimpact.domain.variables import CovariateSpec
from causalimpact.experiments import ExperimentSpec, check_attrition, check_srm_from_assignments
from causalimpact.observational.overlap import check_overlap
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.services import AnalysisResult, AnalysisService, DiagnosticStep
from causalimpact.services.estimator_factory import (
    AIPWConfig,
    EstimatorConfig,
    WeightingConfig,
    build_estimator,
)

logger = logging.getLogger("causalimpact.api")
MAX_ROWS = 1_000_000


class ErrorBody(BaseModel):
    error: str
    detail: str | list[str]
    error_id: str | None = None


class DesignTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to: DesignStatus
    reason: str = Field(min_length=1)


class DatasetPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[dict[str, JsonValue]] = Field(min_length=1, max_length=MAX_ROWS)


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimator: EstimatorConfig
    data: DatasetPayload
    seed: int = Field(ge=0)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)
    experiment: ExperimentSpec | None = Field(
        default=None, description="adds SRM and attrition trust diagnostics (randomized)"
    )
    overlap_covariates: tuple[CovariateSpec, ...] | None = Field(
        default=None, description="defaults to the estimator covariates for propensity methods"
    )


class RunSummary(BaseModel):
    run_id: str
    design_id: str
    status: str
    interpretation: str
    estimate: float | None


class VersionResponse(BaseModel):
    version: str


@dataclass
class ApiState:
    estimands: EstimandRegistry = field(default_factory=EstimandRegistry)
    dags: DagRegistry = field(default_factory=DagRegistry)
    designs: dict[str, StudyDesign] = field(default_factory=dict)
    runs: dict[str, AnalysisResult] = field(default_factory=dict)

    @property
    def service(self) -> AnalysisService:
        return AnalysisService(self.estimands, self.dags)


def _trust_diagnostics(request: RunRequest, estimand: Estimand) -> list[DiagnosticStep]:
    steps: list[DiagnosticStep] = []
    experiment = request.experiment
    if experiment is not None:

        def srm(df: pd.DataFrame) -> DiagnosticResult:
            return check_srm_from_assignments(experiment, df)

        def attrition(df: pd.DataFrame) -> DiagnosticResult:
            return check_attrition(experiment, df, df, estimand.outcome)

        steps += [
            DiagnosticStep("sample_ratio_mismatch", srm),
            DiagnosticStep("attrition", attrition),
        ]
    config = request.estimator
    if isinstance(config, AIPWConfig | WeightingConfig):
        covariates = request.overlap_covariates or config.covariates
        treatment = config.treatment

        def overlap(df: pd.DataFrame) -> DiagnosticResult:
            ps = estimate_propensity(df, treatment, covariates)
            return check_overlap(ps, estimand.type)

        steps.append(DiagnosticStep("overlap", overlap))
    return steps


def create_app(state: ApiState | None = None) -> FastAPI:
    state = state or ApiState()
    app = FastAPI(title="CausalImpact API", version="0.1.0")
    app.state.store = state

    @app.exception_handler(DesignNotReadyError)
    async def not_ready(_: Request, exc: DesignNotReadyError) -> JSONResponse:
        problems = str(exc).split("; ")
        body = ErrorBody(error="design_not_ready", detail=problems)
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        body = ErrorBody(error="domain_rule_violation", detail=str(exc))
        return JSONResponse(status_code=409, content=body.model_dump())

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        body = ErrorBody(error="invalid_request", detail=str(exc))
        return JSONResponse(status_code=422, content=body.model_dump())

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        error_id = uuid.uuid4().hex
        logger.exception("unhandled error %s", error_id, exc_info=exc)
        body = ErrorBody(
            error="internal_error", detail="unexpected server error", error_id=error_id
        )
        return JSONResponse(status_code=500, content=body.model_dump())

    @app.get("/health")
    def health() -> dict[str, Literal["ok"]]:
        return {"status": "ok"}

    @app.post("/estimands", status_code=201)
    def register_estimand(estimand: Estimand) -> Estimand:
        return state.estimands.register(estimand)

    @app.get("/estimands/{estimand_id}")
    def get_estimand(estimand_id: str) -> Estimand:
        if estimand_id not in state.estimands:
            raise HTTPException(404, "estimand not found")
        return state.estimands.get(estimand_id)

    @app.post("/dags", status_code=201)
    def register_dag(dag: CausalDAG) -> VersionResponse:
        return VersionResponse(version=state.dags.register_dag(dag))

    @app.post("/adjustment-sets", status_code=201)
    def register_adjustment_set(adjustment: AdjustmentSet) -> VersionResponse:
        try:
            return VersionResponse(version=state.dags.register_adjustment_set(adjustment))
        except KeyError as exc:
            raise HTTPException(404, str(exc).strip("'")) from None

    @app.post("/designs", status_code=201)
    def create_design(design: StudyDesign) -> StudyDesign:
        if design.status is not DesignStatus.DRAFT or design.status_history:
            raise HTTPException(422, "new designs must be created in Draft")
        if design.design_id in state.designs:
            raise HTTPException(409, "design id already exists")
        state.designs[design.design_id] = design
        return design

    def _design(design_id: str) -> StudyDesign:
        try:
            return state.designs[design_id]
        except KeyError:
            raise HTTPException(404, "design not found") from None

    @app.get("/designs/{design_id}")
    def get_design(design_id: str) -> StudyDesign:
        return _design(design_id)

    @app.post("/designs/{design_id}/transitions")
    def transition_design(design_id: str, request: DesignTransitionRequest) -> StudyDesign:
        design = _design(design_id)
        updated = design.transition(
            request.to,
            reason=request.reason,
            readiness_check=DesignReadinessValidator(state.estimands, state.dags),
        )
        state.designs[design_id] = updated
        return updated

    @app.post("/designs/{design_id}/runs", status_code=201)
    def run_analysis(design_id: str, request: RunRequest) -> AnalysisResult:
        design = _design(design_id)
        if design.estimand_id is None or design.estimand_id not in state.estimands:
            raise DesignNotReadyError("design estimand is not registered")
        estimand = state.estimands.get(design.estimand_id)
        data = pd.DataFrame.from_records(request.data.records)
        estimator = build_estimator(request.estimator, seed=request.seed)
        result = state.service.run(
            design,
            estimator,
            data,
            diagnostics=_trust_diagnostics(request, estimand),
            seed=request.seed,
            confidence_level=request.confidence_level,
        )
        state.runs[result.run.run_id] = result
        return result

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> AnalysisResult:
        try:
            return state.runs[run_id]
        except KeyError:
            raise HTTPException(404, "run not found") from None

    @app.get("/designs/{design_id}/runs")
    def list_runs(design_id: str) -> list[RunSummary]:
        _design(design_id)
        return [
            RunSummary(
                run_id=r.run.run_id,
                design_id=r.run.design_id,
                status=r.run.status.value,
                interpretation=r.interpretation.value,
                estimate=None if r.estimate is None else r.estimate.estimate,
            )
            for r in state.runs.values()
            if r.run.design_id == design_id
        ]

    return app
