"""Sensitivity and robustness analyses."""

from causalimpact.sensitivity.specification import (
    SpecificationGrid,
    SpecificationOutcome,
    SpecificationReport,
    SpecificationVariant,
    SpecStatus,
    run_specifications,
)
from causalimpact.sensitivity.trimming import (
    PolicyKind,
    TrimmingOutcome,
    TrimmingPolicy,
    TrimmingReport,
    run_trimming_sensitivity,
    trimmed_estimand,
)

__all__ = [
    "PolicyKind",
    "SpecStatus",
    "SpecificationGrid",
    "SpecificationOutcome",
    "SpecificationReport",
    "SpecificationVariant",
    "TrimmingOutcome",
    "TrimmingPolicy",
    "TrimmingReport",
    "run_specifications",
    "run_trimming_sensitivity",
    "trimmed_estimand",
]
