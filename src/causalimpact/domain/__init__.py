"""Canonical domain models: StudyDesign, AnalysisRun, estimands and assumptions."""

from causalimpact.domain.analysis_run import ALLOWED_RUN_TRANSITIONS, AnalysisRun, RunStatus
from causalimpact.domain.errors import DesignNotReadyError, DomainError, IllegalTransitionError
from causalimpact.domain.ids import DesignId, RunId, new_design_id, new_run_id
from causalimpact.domain.study_design import (
    ALLOWED_DESIGN_TRANSITIONS,
    ANALYZABLE_STATUSES,
    DesignFamily,
    DesignStatus,
    ReadinessCheck,
    StatusChange,
    StudyDesign,
    TargetPopulation,
    refuse_without_validator,
)
from causalimpact.domain.variables import (
    CovariateDType,
    CovariateSpec,
    DataContract,
    Eligibility,
    EligibilityDecision,
    MissingnessPolicy,
    OutcomeKind,
    OutcomeSpec,
    TreatmentKind,
    TreatmentSpec,
    TriState,
    classify_covariate,
)

__all__ = [
    "ALLOWED_DESIGN_TRANSITIONS",
    "ALLOWED_RUN_TRANSITIONS",
    "ANALYZABLE_STATUSES",
    "AnalysisRun",
    "CovariateDType",
    "CovariateSpec",
    "DataContract",
    "DesignFamily",
    "DesignId",
    "DesignNotReadyError",
    "DesignStatus",
    "DomainError",
    "Eligibility",
    "EligibilityDecision",
    "IllegalTransitionError",
    "MissingnessPolicy",
    "OutcomeKind",
    "OutcomeSpec",
    "ReadinessCheck",
    "RunId",
    "RunStatus",
    "StatusChange",
    "StudyDesign",
    "TargetPopulation",
    "TreatmentKind",
    "TreatmentSpec",
    "TriState",
    "classify_covariate",
    "new_design_id",
    "new_run_id",
    "refuse_without_validator",
]
