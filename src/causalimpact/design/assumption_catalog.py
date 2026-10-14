"""Required identification assumptions per design family (CAUSAL_ASSUMPTIONS.md)."""

from __future__ import annotations

from causalimpact.domain.assumptions import Assumption, Testability
from causalimpact.domain.study_design import DesignFamily


def _a(key: str, statement: str, testability: Testability, *diagnostics: str) -> Assumption:
    return Assumption(
        key=key,
        statement=statement,
        testability=testability,
        related_diagnostics=diagnostics,
    )


_U, _P, _T = Testability.UNTESTABLE, Testability.PARTIALLY_TESTABLE, Testability.TESTABLE

ASSUMPTION_CATALOG: dict[DesignFamily, tuple[Assumption, ...]] = {
    DesignFamily.RANDOMIZED_EXPERIMENT: (
        _a(
            "valid_assignment",
            "Assignment followed the declared randomization mechanism.",
            _P,
            "assignment_integrity",
            "srm",
        ),
        _a(
            "correct_logging",
            "Exposure and outcomes are logged completely and correctly.",
            _P,
            "assignment_integrity",
        ),
        _a("no_interference", "One unit's assignment does not affect another unit's outcome.", _U),
        _a(
            "interpretable_attrition",
            "Missing outcomes do not depend on assignment in a way "
            "that invalidates the comparison.",
            _P,
            "attrition",
        ),
        _a(
            "analysis_matches_randomization",
            "The analysis and its variance estimator respect the randomization unit.",
            _T,
        ),
    ),
    DesignFamily.OBSERVATIONAL: (
        _a(
            "consistency",
            "The observed outcome under the received treatment equals the "
            "corresponding potential outcome.",
            _U,
        ),
        _a(
            "conditional_exchangeability",
            "No unmeasured confounding given the declared adjustment set.",
            _U,
            "negative_controls",
            "sensitivity",
        ),
        _a(
            "positivity",
            "Every covariate pattern in the target population has a non-zero "
            "probability of each treatment level.",
            _P,
            "overlap",
        ),
        _a("temporal_ordering", "Adjustment covariates are measured before treatment.", _P),
        _a(
            "nuisance_adequacy",
            "Nuisance models are sufficiently well specified for the chosen estimator.",
            _P,
            "balance",
        ),
    ),
    DesignFamily.PANEL: (
        _a(
            "parallel_trends",
            "Absent treatment, treated and comparison units would have "
            "followed parallel outcome paths.",
            _U,
            "pre_trends",
        ),
        _a(
            "no_anticipation",
            "Outcomes do not respond to treatment before it starts.",
            _P,
            "pre_trends",
        ),
        _a(
            "pre_treatment_support",
            "There are enough pre-treatment periods to assess the comparison.",
            _T,
        ),
        _a("stable_composition", "Measurement and panel composition are stable over time.", _P),
        _a(
            "timing_handled",
            "Staggered treatment timing is handled by a heterogeneity-robust "
            "estimator when effects may vary.",
            _T,
        ),
    ),
}


def default_assumptions(family: DesignFamily) -> tuple[Assumption, ...]:
    """The required assumptions for a family, unjustified and in status ``assumed``."""
    return ASSUMPTION_CATALOG[family]


def required_assumption_keys(family: DesignFamily) -> frozenset[str]:
    return frozenset(a.key for a in ASSUMPTION_CATALOG[family])
