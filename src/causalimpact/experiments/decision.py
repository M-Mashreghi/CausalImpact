"""Metric roles, multiplicity corrections and experiment decision labels (Task 2.8).

A ``DecisionPolicy`` must be declared (and is fingerprinted) before any decision label is
produced. Roles:

* **primary**: exactly one metric; its two-sided test at ``alpha`` drives the label.
* **guardrails**: harm checks with a declared tolerable degradation. They are *not*
  multiplicity-adjusted: adjustment would make harm harder to detect, which is the unsafe
  direction for a guardrail.
* **secondary**: reported with p-values adjusted by the declared method; they inform
  but never drive the label.

Labels: ``blocked`` (a trust diagnostic is blocking), ``no_ship``, ``inconclusive``,
``ship``. A label is a decision under the declared policy, not a causal claim beyond the
experiment's ITT estimand.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Self

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from causalimpact.diagnostics.base import DiagnosticResult
from causalimpact.domain.estimands import EffectEstimate
from causalimpact.domain.fingerprint import content_hash
from causalimpact.domain.types import AwareDatetime, NonBlankStr
from causalimpact.experiments.spec import ExperimentSpec


class CorrectionMethod(StrEnum):
    NONE = "none"
    BONFERRONI = "bonferroni"
    HOLM = "holm"
    BENJAMINI_HOCHBERG = "benjamini_hochberg"


def adjust_p_values(p_values: Sequence[float], method: CorrectionMethod) -> list[float]:
    """Adjusted p-values (same order as input), as in R's ``p.adjust``."""
    p = np.asarray(p_values, dtype=float)
    if p.ndim != 1 or np.any((p < 0) | (p > 1)) or np.any(np.isnan(p)):
        raise ValueError("p-values must be a 1-D sequence in [0, 1]")
    m = p.size
    if m == 0 or method is CorrectionMethod.NONE:
        return [float(x) for x in p]
    if method is CorrectionMethod.BONFERRONI:
        return [float(x) for x in np.minimum(p * m, 1.0)]
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    if method is CorrectionMethod.HOLM:
        stepped = np.maximum.accumulate((m - np.arange(m)) * ranked)
    else:  # Benjamini-Hochberg
        stepped = np.minimum.accumulate((m / np.arange(m, 0, -1)) * ranked[::-1])[::-1]
    adjusted = np.empty(m)
    adjusted[order] = np.minimum(stepped, 1.0)
    return [float(x) for x in adjusted]


class Direction(StrEnum):
    INCREASE_IS_BETTER = "increase_is_better"
    DECREASE_IS_BETTER = "decrease_is_better"


class GuardrailRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric: NonBlankStr
    direction: Direction
    max_degradation: float = Field(ge=0.0, description="tolerable harm, in effect units")


class DecisionPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: NonBlankStr
    declared_at: AwareDatetime
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    primary_direction: Direction = Direction.INCREASE_IS_BETTER
    secondary_correction: CorrectionMethod = CorrectionMethod.HOLM
    guardrails: tuple[GuardrailRule, ...] = ()

    @model_validator(mode="after")
    def _unique_guardrails(self) -> Self:
        names = [g.metric for g in self.guardrails]
        if len(names) != len(set(names)):
            raise ValueError("duplicate guardrail rules")
        return self

    @property
    def fingerprint(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class DecisionLabel(StrEnum):
    BLOCKED = "blocked"
    NO_SHIP = "no_ship"
    INCONCLUSIVE = "inconclusive"
    SHIP = "ship"


class GuardrailStatus(StrEnum):
    CLEARED = "cleared"
    VIOLATED = "violated"
    UNRESOLVED = "unresolved"


class Decision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    experiment_id: str
    label: DecisionLabel
    reasons: tuple[str, ...]
    policy_fingerprint: str
    primary: dict[str, JsonValue]
    guardrails: dict[str, GuardrailStatus]
    secondary: tuple[dict[str, JsonValue], ...]


def _signed(effect: float, direction: Direction) -> float:
    return effect if direction is Direction.INCREASE_IS_BETTER else -effect


def guardrail_status(rule: GuardrailRule, estimate: EffectEstimate) -> GuardrailStatus:
    """Harm = degradation in the bad direction. Violated if harm is significant; unresolved
    if the interval cannot rule out harm beyond the tolerable degradation."""
    if rule.direction is Direction.INCREASE_IS_BETTER:
        worst, best = -estimate.ci_lower, -estimate.ci_upper
    else:
        worst, best = estimate.ci_upper, estimate.ci_lower
    if best > 0:
        return GuardrailStatus.VIOLATED
    if worst > rule.max_degradation:
        return GuardrailStatus.UNRESOLVED
    return GuardrailStatus.CLEARED


def decide(
    spec: ExperimentSpec,
    policy: DecisionPolicy,
    results: Mapping[str, EffectEstimate],
    trust_diagnostics: Sequence[DiagnosticResult],
    *,
    analysed_at: datetime,
) -> Decision:
    if policy.experiment_id != spec.experiment_id:
        raise ValueError("policy belongs to a different experiment")
    if policy.declared_at > analysed_at:
        raise ValueError("the decision policy must be declared before results are analysed")
    guardrail_rules = {g.metric: g for g in policy.guardrails}
    if set(guardrail_rules) != set(spec.guardrail_metrics):
        raise ValueError("every guardrail metric needs exactly one declared rule")
    required = [spec.primary_metric, *spec.guardrail_metrics, *spec.secondary_metrics]
    if missing := [m for m in required if m not in results]:
        raise ValueError(f"missing results for metrics {missing}")
    level = 1 - policy.alpha
    if wrong := [m for m in required if not np.isclose(results[m].confidence_level, level)]:
        raise ValueError(f"results not computed at confidence level {level}: {wrong}")

    reasons: list[str] = []
    blocking = [d for d in trust_diagnostics if d.is_blocking]
    for diag in blocking:
        reasons.append(f"trust check '{diag.name}' is blocking: {sorted(diag.codes())}")

    primary = results[spec.primary_metric]
    if primary.p_value is None:
        raise ValueError("primary result needs a p-value")
    significant = primary.p_value < policy.alpha
    improvement = _signed(primary.estimate, policy.primary_direction) > 0

    guardrails = {
        m: guardrail_status(guardrail_rules[m], results[m]) for m in spec.guardrail_metrics
    }

    secondary_p = [results[m].p_value for m in spec.secondary_metrics]
    if any(p is None for p in secondary_p):
        raise ValueError("secondary results need p-values")
    adjusted = adjust_p_values(
        [p for p in secondary_p if p is not None], policy.secondary_correction
    )
    secondary = tuple(
        {
            "metric": m,
            "estimate": results[m].estimate,
            "ci_lower": results[m].ci_lower,
            "ci_upper": results[m].ci_upper,
            "p_value": results[m].p_value,
            "adjusted_p_value": adj,
            "correction": policy.secondary_correction.value,
        }
        for m, adj in zip(spec.secondary_metrics, adjusted, strict=True)
    )

    if blocking:
        label = DecisionLabel.BLOCKED
    elif violated := [m for m, s in guardrails.items() if s is GuardrailStatus.VIOLATED]:
        label = DecisionLabel.NO_SHIP
        reasons.append(f"guardrails violated: {violated}")
    elif significant and not improvement:
        label = DecisionLabel.NO_SHIP
        reasons.append("primary metric significantly worse")
    elif unresolved := [m for m, s in guardrails.items() if s is GuardrailStatus.UNRESOLVED]:
        label = DecisionLabel.INCONCLUSIVE
        reasons.append(f"cannot rule out guardrail harm beyond tolerance: {unresolved}")
    elif significant:
        label = DecisionLabel.SHIP
        reasons.append("primary metric significantly better; guardrails cleared")
    else:
        label = DecisionLabel.INCONCLUSIVE
        reasons.append("primary metric not significant at the declared alpha")

    return Decision(
        experiment_id=spec.experiment_id,
        label=label,
        reasons=tuple(reasons),
        policy_fingerprint=policy.fingerprint,
        primary={
            "metric": spec.primary_metric,
            "estimate": primary.estimate,
            "ci_lower": primary.ci_lower,
            "ci_upper": primary.ci_upper,
            "p_value": primary.p_value,
            "estimand_id": primary.estimand_id,
        },
        guardrails=guardrails,
        secondary=secondary,
    )
