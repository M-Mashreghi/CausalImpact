"""Estimator / specification comparison with estimand compatibility checks (Task 6.5).

Two estimates are comparable only if they answer the same question: same estimand type,
treatment, outcome, effect scale and target population, at the same confidence level.
Estimates are grouped by that compatibility key; incompatible estimates are placed in
separate groups and a blocking finding explains why they must not be read side by side.

Comparison never ranks: members keep their input order and no "best" estimate is chosen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, JsonValue

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandMismatchError
from causalimpact.domain.fingerprint import content_hash


@dataclass(frozen=True)
class LabelledEstimate:
    label: str
    estimand: Estimand
    estimate: EffectEstimate


def compatibility_key(item: LabelledEstimate) -> str:
    e = item.estimand
    return content_hash(
        {
            "type": e.type.value,
            "treatment": e.treatment,
            "outcome": e.outcome,
            "scale": e.scale.value,
            "treatment_basis": e.treatment_basis.value,
            "conditioning": list(e.conditioning_variables),
            "population": e.target_population.model_dump(mode="json"),
            "confidence_level": item.estimate.confidence_level,
        }
    )


def incompatibilities(a: LabelledEstimate, b: LabelledEstimate) -> list[str]:
    ea, eb = a.estimand, b.estimand
    reasons: list[str] = []
    for attr in ("type", "treatment", "outcome", "scale", "treatment_basis"):
        if getattr(ea, attr) != getattr(eb, attr):
            reasons.append(f"{attr}: {getattr(ea, attr)} vs {getattr(eb, attr)}")
    if ea.conditioning_variables != eb.conditioning_variables:
        reasons.append("conditioning variables differ")
    if ea.target_population != eb.target_population:
        reasons.append(
            f"target population: {ea.target_population.name!r} vs {eb.target_population.name!r}"
        )
    if a.estimate.confidence_level != b.estimate.confidence_level:
        reasons.append("confidence levels differ")
    return reasons


def ensure_comparable(a: LabelledEstimate, b: LabelledEstimate) -> None:
    if reasons := incompatibilities(a, b):
        raise EstimandMismatchError(
            f"'{a.label}' and '{b.label}' target different estimands: " + "; ".join(reasons)
        )


class ComparisonGroup(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    compatibility_key: str
    estimand_description: str
    members: tuple[dict[str, JsonValue], ...]


class ComparisonReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    groups: tuple[ComparisonGroup, ...]
    diagnostic: DiagnosticResult

    @property
    def all_comparable(self) -> bool:
        return len(self.groups) <= 1


def compare_estimates(items: Sequence[LabelledEstimate]) -> ComparisonReport:
    labels = [i.label for i in items]
    if len(labels) != len(set(labels)):
        raise ValueError("comparison labels must be unique")
    grouped: dict[str, list[LabelledEstimate]] = {}
    for item in items:
        grouped.setdefault(compatibility_key(item), []).append(item)

    groups: list[ComparisonGroup] = []
    for key, members in grouped.items():
        reference = members[0]
        e = reference.estimand
        groups.append(
            ComparisonGroup(
                compatibility_key=key,
                estimand_description=(
                    f"{e.type} of {e.treatment} on {e.outcome} ({e.scale}) in "
                    f"{e.target_population.name}, {reference.estimate.confidence_level:.0%} CI"
                ),
                members=tuple(
                    {
                        "label": m.label,
                        "estimand_id": m.estimand.estimand_id,
                        "estimator": m.estimate.estimator,
                        "estimate": m.estimate.estimate,
                        "std_error": m.estimate.std_error,
                        "ci_lower": m.estimate.ci_lower,
                        "ci_upper": m.estimate.ci_upper,
                        "difference_from_first": m.estimate.estimate - reference.estimate.estimate,
                    }
                    for m in members
                ),
            )
        )

    findings: list[Finding] = []
    if len(groups) > 1:
        first = items[0]
        details = [
            f"{other.label}: {'; '.join(incompatibilities(first, other))}"
            for other in items[1:]
            if incompatibilities(first, other)
        ]
        findings.append(
            Finding(
                code="incompatible_estimands",
                severity=FindingSeverity.BLOCKING,
                message=(
                    f"{len(groups)} incompatible estimand groups; estimates in different "
                    "groups answer different questions and must not be compared or ranked "
                    "as if identical"
                ),
                count=len(groups),
                examples=tuple(details[:5]),
            )
        )
    diagnostic = DiagnosticResult(
        name="estimate_comparison",
        findings=tuple(findings),
        metrics={"n_estimates": len(items), "n_groups": len(groups)},
        notes=("members are listed in input order; comparison does not rank estimators",),
    )
    return ComparisonReport(groups=tuple(groups), diagnostic=diagnostic)
