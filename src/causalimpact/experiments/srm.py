"""Sample Ratio Mismatch detection and triage (Task 2.2).

Observed unit counts per arm are compared with the configured allocation using Pearson's
chi-square goodness-of-fit test. With two arms and any expected count below 5 the exact
binomial test is used instead; with more arms and small expected counts the test is
reported as unreliable (warning) rather than silently trusted.

A detected SRM is *blocking*: the experiment is untrustworthy until the root cause is
found (RUNBOOK.md, "SRM detected"). The conventional, deliberately strict threshold is
p < 0.001.
"""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.experiments.spec import ExperimentSpec

NAME = "sample_ratio_mismatch"
DEFAULT_SRM_ALPHA = 0.001
MIN_EXPECTED_COUNT = 5.0

TRIAGE_CHECKLIST = (
    "assignment / bucketing configuration and ramp changes",
    "exposure or trigger logging loss in one arm",
    "telemetry or bot filtering applied unevenly across arms",
    "joins or filters that drop units differently by arm",
    "triggered-analysis filters correlated with the treatment",
)


def check_srm(
    spec: ExperimentSpec,
    observed: Mapping[str, int],
    *,
    alpha: float = DEFAULT_SRM_ALPHA,
) -> DiagnosticResult:
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    if unknown := set(observed) - set(spec.arm_names):
        raise ValueError(f"counts for arms not in the design: {sorted(unknown)}")
    if any(v < 0 for v in observed.values()):
        raise ValueError("counts must be non-negative")

    arms = spec.arm_names
    counts = [int(observed.get(a, 0)) for a in arms]
    total = sum(counts)
    if total == 0:
        return DiagnosticResult(
            name=NAME,
            findings=(
                Finding(
                    code="no_units",
                    severity=FindingSeverity.BLOCKING,
                    message="no assigned units; SRM cannot be assessed",
                ),
            ),
        )
    expected = [total * spec.allocation[a] for a in arms]

    findings: list[Finding] = []
    small = min(expected) < MIN_EXPECTED_COUNT
    if len(arms) == 2 and small:
        method = "exact_binomial"
        statistic = None
        p_value = float(stats.binomtest(counts[0], total, spec.allocation[arms[0]]).pvalue)
    else:
        method = "chi_square"
        result = stats.chisquare(counts, f_exp=expected)
        statistic = float(result.statistic)
        p_value = float(result.pvalue)
        if small:
            findings.append(
                Finding(
                    code="srm_test_unreliable",
                    severity=FindingSeverity.WARNING,
                    message=f"expected count below {MIN_EXPECTED_COUNT:g} in some arm; the "
                    "chi-square approximation is unreliable",
                )
            )

    observed_ratio = {a: c / total for a, c in zip(arms, counts, strict=True)}
    if p_value < alpha:
        worst = max(arms, key=lambda a: abs(observed_ratio[a] - spec.allocation[a]))
        findings.append(
            Finding(
                code="srm_detected",
                severity=FindingSeverity.BLOCKING,
                message=(
                    f"sample ratio mismatch (p={p_value:.3g} < {alpha:g}); largest deviation "
                    f"in arm {worst!r}: observed share {observed_ratio[worst]:.4f} vs "
                    f"configured {spec.allocation[worst]:.4f}. Treat the experiment as "
                    "untrustworthy until the root cause is resolved."
                ),
                count=total,
                examples=(worst,),
            )
        )

    metrics = {
        "method": method,
        "alpha": alpha,
        "statistic": statistic,
        "degrees_of_freedom": len(arms) - 1,
        "p_value": p_value,
        "total_units": total,
        "observed": dict(zip(arms, counts, strict=True)),
        "expected": dict(zip(arms, expected, strict=True)),
        "configured_allocation": dict(spec.allocation),
        "observed_allocation": observed_ratio,
    }
    notes = ("triage: check " + "; ".join(TRIAGE_CHECKLIST),) if p_value < alpha else ()
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics, notes=notes)


def check_srm_from_assignments(
    spec: ExperimentSpec, assignments: pd.DataFrame, *, alpha: float = DEFAULT_SRM_ALPHA
) -> DiagnosticResult:
    """SRM on unique randomization units per arm (run assignment integrity first)."""
    units = assignments.dropna(subset=[spec.randomization_unit, spec.arm_column])
    units = units.drop_duplicates(subset=[spec.randomization_unit, spec.arm_column])
    counts = units[spec.arm_column].value_counts()
    return check_srm(spec, {str(k): int(v) for k, v in counts.items()}, alpha=alpha)
