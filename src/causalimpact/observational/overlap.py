"""Overlap / positivity diagnostics for propensity-based estimation (Task 3.3).

Which units need overlap depends on the estimand:

* ATE needs every unit to have propensity strictly inside (eps, 1 - eps);
* ATT needs comparable controls for treated units: treated propensities below 1 - eps;
* ATC needs comparable treated units for controls: control propensities above eps.

Reported: per-arm propensity quantiles and plot-ready histograms, the common-support
interval, estimand-relevant violation counts, and Kish effective sample sizes of the
estimand's inverse-probability weights. Thresholds come from an explicit, recorded
``OverlapPolicy``. A blocking result means estimation must refuse rather than extrapolate.
"""

from __future__ import annotations

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.estimands import EstimandType
from causalimpact.observational.propensity import PropensityScores

NAME = "overlap"
SUPPORTED = frozenset({EstimandType.ATE, EstimandType.ATT, EstimandType.ATC})


class OverlapPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    epsilon: float = Field(default=0.01, gt=0.0, lt=0.5)
    warn_violation_fraction: float = Field(default=0.0, ge=0.0, le=1.0)
    block_violation_fraction: float = Field(default=0.05, ge=0.0, le=1.0)
    warn_ess_fraction: float = Field(default=0.3, gt=0.0, le=1.0)
    block_ess_fraction: float = Field(default=0.1, gt=0.0, le=1.0)
    histogram_bins: int = Field(default=20, ge=2)


class OverlapRefusedError(RuntimeError):
    """Estimation was attempted although the overlap diagnostic is blocking."""


def estimand_weights(scores: np.ndarray, treated: np.ndarray, estimand: EstimandType) -> np.ndarray:
    """Unnormalised inverse-probability weights targeting ``estimand``."""
    t = treated.astype(bool)
    if estimand is EstimandType.ATE:
        return np.where(t, 1.0 / scores, 1.0 / (1.0 - scores))
    if estimand is EstimandType.ATT:
        return np.where(t, 1.0, scores / (1.0 - scores))
    if estimand is EstimandType.ATC:
        return np.where(t, (1.0 - scores) / scores, 1.0)
    raise ValueError(f"no propensity weights for {estimand}")


def kish_ess(weights: np.ndarray) -> float:
    return float(weights.sum() ** 2 / np.sum(weights**2)) if weights.size else 0.0


def check_overlap(
    propensity: PropensityScores,
    estimand: EstimandType,
    policy: OverlapPolicy | None = None,
) -> DiagnosticResult:
    policy = policy or OverlapPolicy()
    if estimand not in SUPPORTED:
        raise ValueError(f"overlap diagnostics support {sorted(SUPPORTED)}, not {estimand}")
    e = np.asarray(propensity.scores, dtype=float)
    t = np.asarray(propensity.treated, dtype=bool)
    eps = policy.epsilon
    low, high = e <= eps, e >= 1 - eps

    if estimand is EstimandType.ATE:
        relevant, violating = np.ones_like(t), low | high
    elif estimand is EstimandType.ATT:
        relevant, violating = t, t & high
    else:
        relevant, violating = ~t, (~t) & low
    n_relevant = int(relevant.sum())
    n_violating = int(violating.sum())
    violation_fraction = n_violating / n_relevant if n_relevant else 1.0

    clipped = np.clip(e, 1e-12, 1 - 1e-12)  # only to keep weights finite for reporting
    weights = estimand_weights(clipped, t, estimand)
    ess = {"treated": kish_ess(weights[t]), "control": kish_ess(weights[~t])}
    ess_fraction = {
        "treated": ess["treated"] / max(int(t.sum()), 1),
        "control": ess["control"] / max(int((~t).sum()), 1),
    }
    # For ATT the treated weights are constant; only the control side can degrade.
    constrained = {
        EstimandType.ATE: ("treated", "control"),
        EstimandType.ATT: ("control",),
        EstimandType.ATC: ("treated",),
    }[estimand]
    worst_ess = min(ess_fraction[a] for a in constrained)

    findings: list[Finding] = []
    if violation_fraction > policy.block_violation_fraction:
        severity = FindingSeverity.BLOCKING
    elif violation_fraction > policy.warn_violation_fraction:
        severity = FindingSeverity.WARNING
    else:
        severity = None
    if severity is not None:
        findings.append(
            Finding(
                code="positivity_violation",
                severity=severity,
                message=(
                    f"{n_violating} of {n_relevant} {estimand}-relevant units have propensity "
                    f"outside ({eps:g}, {1 - eps:g}); estimates there rely on extrapolation"
                ),
                count=n_violating,
            )
        )
    if worst_ess < policy.block_ess_fraction:
        severity = FindingSeverity.BLOCKING
    elif worst_ess < policy.warn_ess_fraction:
        severity = FindingSeverity.WARNING
    else:
        severity = None
    if severity is not None:
        findings.append(
            Finding(
                code="low_effective_sample_size",
                severity=severity,
                message=f"weighted effective sample size is {worst_ess:.1%} of the arm size",
            )
        )

    bins = np.linspace(0.0, 1.0, policy.histogram_bins + 1)
    quantile_levels = (0.0, 0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99, 1.0)

    def summary(mask: np.ndarray) -> dict[str, JsonValue]:
        values = e[mask]
        return {
            "n": int(mask.sum()),
            "quantiles": {f"{q:g}": float(np.quantile(values, q)) for q in quantile_levels}
            if values.size
            else {},
            "histogram": [int(c) for c in np.histogram(values, bins=bins)[0]],
        }

    support = (
        float(max(e[t].min(), e[~t].min())),
        float(min(e[t].max(), e[~t].max())),
    )
    metrics: dict[str, JsonValue] = {
        "estimand": estimand.value,
        "policy": policy.model_dump(mode="json"),
        "n_relevant": n_relevant,
        "n_violating": n_violating,
        "violation_fraction": violation_fraction,
        "common_support": list(support),
        "outside_common_support": int(np.sum((e < support[0]) | (e > support[1]))),
        "effective_sample_size": dict(ess),
        "ess_fraction": dict(ess_fraction),
        "histogram_bin_edges": [float(b) for b in bins],
        "treated": summary(t),
        "control": summary(~t),
    }
    notes = (
        "overlap diagnostics show where the data support comparison; they cannot verify "
        "that the propensity model or the adjustment set is correct",
    )
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics, notes=notes)


def ensure_overlap(result: DiagnosticResult) -> None:
    """Raise if an overlap diagnostic is blocking (estimators call this before fitting)."""
    if result.name != NAME:
        raise ValueError("expected an overlap diagnostic")
    if result.is_blocking:
        raise OverlapRefusedError(
            "overlap is insufficient for the target estimand: "
            + "; ".join(f.message for f in result.findings if f.severity == "blocking")
        )
