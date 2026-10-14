"""Application services orchestrating design to report."""

from causalimpact.services.analysis import (
    AnalysisResult,
    AnalysisService,
    DiagnosticStep,
    InterpretationStatus,
    interpret,
)
from causalimpact.services.comparison import (
    ComparisonGroup,
    ComparisonReport,
    LabelledEstimate,
    compare_estimates,
    ensure_comparable,
)
from causalimpact.services.registry import (
    AnalysisRegistry,
    BundleIntegrityError,
    RerunCheck,
    export_bundle,
    rerun_bundle,
)
from causalimpact.services.run_spec import DiagnosticsConfig, RunSpec, execute

__all__ = [
    "AnalysisRegistry",
    "AnalysisResult",
    "AnalysisService",
    "BundleIntegrityError",
    "ComparisonGroup",
    "ComparisonReport",
    "DiagnosticStep",
    "DiagnosticsConfig",
    "InterpretationStatus",
    "LabelledEstimate",
    "RerunCheck",
    "RunSpec",
    "compare_estimates",
    "ensure_comparable",
    "execute",
    "export_bundle",
    "interpret",
    "rerun_bundle",
]
