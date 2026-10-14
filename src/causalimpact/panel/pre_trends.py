"""Pre-trend diagnostics from an event study (Task 4.5).

Uses the pre-period relative-time coefficients (all k < reference): individual
estimates and intervals, a joint Wald test that they are all zero (F with (q, G - 1)
degrees of freedom, using the clustered covariance), and the slope of a linear trend
through them.

A detected pre-trend is blocking for a *clean* causal DiD interpretation (RUNBOOK.md,
"DiD pre-period problem"). Passing the test never proves parallel trends: it can lack
power, and parallel trends concern the unobserved post-period counterfactual. That
caveat is always attached.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from pydantic import JsonValue
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity

NAME = "pre_trends"
CAVEAT = (
    "a non-significant pre-trend test does not prove parallel trends: the test may be "
    "underpowered and parallel trends concern unobserved post-treatment counterfactuals"
)


def check_pre_trends(event_study: DiagnosticResult, *, alpha: float = 0.05) -> DiagnosticResult:
    if event_study.name != "event_study_twfe":
        raise ValueError("expected an event-study diagnostic")
    metrics: dict[str, Any] = dict(event_study.metrics)  # JSON produced by twfe_event_study
    reference = int(metrics["reference_relative_time"])
    order = [int(k) for k in metrics["coefficient_order"]]
    cov = np.asarray(metrics["covariance"], dtype=float)
    coef_by_k = {int(c["relative_time"]): float(c["coef"]) for c in metrics["coefficients"]}
    pre = [i for i, k in enumerate(order) if k < reference]
    findings: list[Finding] = []
    pre_metrics: dict[str, JsonValue] = {
        "alpha": alpha,
        "reference_relative_time": reference,
        "pre_periods": [order[i] for i in pre],
    }
    if not pre:
        findings.append(
            Finding(
                code="no_pre_period_coefficients",
                severity=FindingSeverity.WARNING,
                message="no pre-period coefficients besides the reference; pre-trends "
                "cannot be assessed at all",
            )
        )
        return DiagnosticResult(
            name=NAME, findings=tuple(findings), metrics=pre_metrics, notes=(CAVEAT,)
        )

    b = np.array([coef_by_k[order[i]] for i in pre])
    v = cov[np.ix_(pre, pre)]
    q = len(pre)
    g = int(metrics["n_clusters"])
    wald = float(b @ np.linalg.solve(v, b))
    f_stat = wald / q
    p_value = float(stats.f.sf(f_stat, q, g - 1))

    ks = np.array([order[i] for i in pre] + [reference], dtype=float)
    path = np.append(b, 0.0)
    slope = float(np.polyfit(ks, path, 1)[0]) if len(ks) >= 2 else None

    pre_metrics |= {
        "coefficients": {str(order[i]): float(coef) for i, coef in zip(pre, b, strict=True)},
        "max_abs_pre_coefficient": float(np.max(np.abs(b))),
        "joint_f_statistic": f_stat,
        "joint_df": [q, g - 1],
        "joint_p_value": p_value,
        "linear_pre_trend_slope": slope,
    }
    if p_value < alpha:
        findings.append(
            Finding(
                code="pre_trend_detected",
                severity=FindingSeverity.BLOCKING,
                message=(
                    f"pre-period coefficients are jointly non-zero (F={f_stat:.2f}, "
                    f"p={p_value:.3g}); do not present the DiD as cleanly causal. Revisit "
                    "comparison groups and timing, or report robust alternatives."
                ),
                count=q,
            )
        )
    return DiagnosticResult(
        name=NAME, findings=tuple(findings), metrics=pre_metrics, notes=(CAVEAT,)
    )
