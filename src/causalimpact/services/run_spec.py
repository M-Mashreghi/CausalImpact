"""Declarative, serialisable analysis specification.

A ``RunSpec`` fully describes how to re-run an analysis: the whitelisted estimator
configuration, the trust diagnostics to apply, the seed and the confidence level.
Because it is plain data it can be stored, exported in a reproducibility bundle and
replayed (Task 6.7); the API accepts the same structure (Task 6.2).
"""

from __future__ import annotations

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from causalimpact.diagnostics.base import DiagnosticResult
from causalimpact.domain.errors import DesignNotReadyError
from causalimpact.domain.estimands import Estimand
from causalimpact.domain.study_design import StudyDesign
from causalimpact.domain.variables import CovariateSpec
from causalimpact.experiments.attrition import check_attrition
from causalimpact.experiments.spec import ExperimentSpec
from causalimpact.experiments.srm import check_srm_from_assignments
from causalimpact.observational.overlap import check_overlap
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.services.analysis import AnalysisResult, AnalysisService, DiagnosticStep
from causalimpact.services.estimator_factory import (
    AIPWConfig,
    EstimatorConfig,
    WeightingConfig,
    build_estimator,
)


class DiagnosticsConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment: ExperimentSpec | None = Field(
        default=None, description="adds SRM and attrition trust diagnostics (randomized)"
    )
    overlap_covariates: tuple[CovariateSpec, ...] | None = Field(
        default=None, description="defaults to the estimator covariates for propensity methods"
    )


class RunSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    estimator: EstimatorConfig
    diagnostics: DiagnosticsConfig = Field(default_factory=DiagnosticsConfig)
    seed: int = Field(ge=0)
    confidence_level: float = Field(default=0.95, gt=0.0, lt=1.0)


def build_diagnostics(spec: RunSpec, estimand: Estimand) -> list[DiagnosticStep]:
    steps: list[DiagnosticStep] = []
    experiment = spec.diagnostics.experiment
    if experiment is not None:

        def srm(df: pd.DataFrame) -> DiagnosticResult:
            return check_srm_from_assignments(experiment, df)

        def attrition(df: pd.DataFrame) -> DiagnosticResult:
            return check_attrition(experiment, df, df, estimand.outcome)

        steps += [
            DiagnosticStep("sample_ratio_mismatch", srm),
            DiagnosticStep("attrition", attrition),
        ]
    config = spec.estimator
    if isinstance(config, AIPWConfig | WeightingConfig):
        covariates = spec.diagnostics.overlap_covariates or config.covariates
        treatment = config.treatment

        def overlap(df: pd.DataFrame) -> DiagnosticResult:
            ps = estimate_propensity(df, treatment, covariates)
            return check_overlap(ps, estimand.type)

        steps.append(DiagnosticStep("overlap", overlap))
    return steps


def execute(
    service: AnalysisService, design: StudyDesign, spec: RunSpec, data: pd.DataFrame
) -> AnalysisResult:
    """Run ``spec`` against ``design`` through the analysis service."""
    if design.estimand_id is None or design.estimand_id not in service.estimands:
        raise DesignNotReadyError("design estimand is not registered")
    estimand = service.estimands.get(design.estimand_id)
    return service.run(
        design,
        build_estimator(spec.estimator, seed=spec.seed),
        data,
        diagnostics=build_diagnostics(spec, estimand),
        seed=spec.seed,
        confidence_level=spec.confidence_level,
    )
