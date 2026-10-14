"""Cluster-robust inference configuration and validity checks (Task 4.6).

CR1 cluster-robust standard errors with t(G - 1) critical values are reliable only with
enough clusters, and DiD inference additionally needs enough *treated* clusters
(Conley & Taber 2011). ``check_clusters`` reports cluster counts and sizes, warns below
``warn_below`` clusters (or treated clusters) and refuses below ``refuse_below``.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.estimators.ols import ols_cluster_robust

NAME = "cluster_inference"


class ClusterPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    warn_below: int = Field(default=30, ge=2)
    refuse_below: int = Field(default=5, ge=2)
    warn_treated_below: int = Field(default=5, ge=1)


class ClusterInferenceError(ValueError):
    """Too few clusters for the requested cluster-robust inference."""


def check_clusters(
    clusters: np.ndarray,
    treated: np.ndarray | None = None,
    policy: ClusterPolicy | None = None,
) -> DiagnosticResult:
    policy = policy or ClusterPolicy()
    labels, counts = np.unique(clusters, return_counts=True)
    g = int(labels.size)
    findings: list[Finding] = []
    metrics: dict[str, JsonValue] = {
        "n_clusters": g,
        "min_cluster_size": int(counts.min()),
        "max_cluster_size": int(counts.max()),
        "policy": policy.model_dump(),
    }
    if g < policy.refuse_below:
        findings.append(
            Finding(
                code="too_few_clusters",
                severity=FindingSeverity.BLOCKING,
                message=f"{g} clusters is below the minimum of {policy.refuse_below}; "
                "cluster-robust inference is not supported",
            )
        )
    elif g < policy.warn_below:
        findings.append(
            Finding(
                code="few_clusters",
                severity=FindingSeverity.WARNING,
                message=f"only {g} clusters: CR1 standard errors may be too small; "
                "consider a wild cluster bootstrap or randomization inference",
            )
        )
    if treated is not None:
        t = np.asarray(treated, dtype=bool)
        n_treated = int(np.unique(clusters[t]).size)
        metrics["n_treated_clusters"] = n_treated
        if n_treated < policy.warn_treated_below:
            findings.append(
                Finding(
                    code="few_treated_clusters",
                    severity=FindingSeverity.WARNING,
                    message=f"only {n_treated} treated clusters: cluster-robust DiD inference "
                    "is unreliable with few treated groups (Conley & Taber 2011)",
                )
            )
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics)


def clustered_mean_difference(
    values: np.ndarray, treated: np.ndarray, clusters: np.ndarray, confidence_level: float
) -> tuple[float, float, float, float]:
    """Difference in means of ``values`` (treated - control) with CR1 SE clustered on
    ``clusters``; returns (estimate, se, degrees of freedom, critical value)."""
    t = np.asarray(treated, dtype=float)
    design = np.column_stack([np.ones_like(t), t])
    fit = ols_cluster_robust(design, np.asarray(values, dtype=float), clusters)
    g = int(np.unique(clusters).size)
    df = float(g - 1)
    crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))
    return float(fit.coef[1]), math.sqrt(float(fit.cov[1, 1])), df, crit


def ensure_clusters(result: DiagnosticResult) -> None:
    if result.is_blocking:
        raise ClusterInferenceError("; ".join(f.message for f in result.findings))
