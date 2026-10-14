"""Observational causal inference: propensity, matching, weighting, AIPW, DML."""

from causalimpact.observational.eligibility import (
    CovariateScreen,
    VariableDecision,
    screen_adjustment_candidates,
)
from causalimpact.observational.matching import (
    MatchingConfig,
    MatchResult,
    match_on_propensity,
    matched_sample_diagnostics,
)
from causalimpact.observational.overlap import (
    OverlapPolicy,
    OverlapRefusedError,
    check_overlap,
    ensure_overlap,
    estimand_weights,
    kish_ess,
)
from causalimpact.observational.propensity import (
    ConvergenceError,
    LogisticPropensity,
    PropensityModel,
    PropensityScores,
    estimate_propensity,
)

__all__ = [
    "ConvergenceError",
    "CovariateScreen",
    "LogisticPropensity",
    "MatchResult",
    "MatchingConfig",
    "OverlapPolicy",
    "OverlapRefusedError",
    "PropensityModel",
    "PropensityScores",
    "VariableDecision",
    "check_overlap",
    "ensure_overlap",
    "estimand_weights",
    "estimate_propensity",
    "kish_ess",
    "match_on_propensity",
    "matched_sample_diagnostics",
    "screen_adjustment_candidates",
]
