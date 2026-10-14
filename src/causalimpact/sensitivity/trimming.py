"""Weight trimming / overlap sensitivity across pre-declared policies (Task 5.3).

Two kinds of policy have different consequences, and the report keeps them apart:

* **Propensity trimming** (keep units with alpha <= e(x) <= 1 - alpha, Crump et al. 2009)
  drops units, so it *changes the target population*. The result is reported against a
  derived estimand whose id and target population record the restriction; it is never
  presented as the original estimand.
* **Weight truncation** (cap weights at a within-arm quantile) keeps every unit, so the
  estimand is unchanged, but the estimator becomes biased for it; this is flagged.

The propensity model used to define trimmed populations is fitted once on the full data
and recorded. Every declared policy appears in the output, including failures.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from causalimpact.domain.estimands import EffectEstimate, Estimand
from causalimpact.domain.fingerprint import content_hash
from causalimpact.domain.study_design import TargetPopulation
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.observational.weighting import WeightingEstimator


class PolicyKind(StrEnum):
    NONE = "none"
    PROPENSITY_TRIM = "propensity_trim"
    WEIGHT_TRUNCATION = "weight_truncation"


class TrimmingPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: PolicyKind
    alpha: float | None = Field(default=None, gt=0.0, lt=0.5)
    quantile: float | None = Field(default=None, gt=0.5, lt=1.0)

    def model_post_init(self, __context: object) -> None:
        if self.kind is PolicyKind.PROPENSITY_TRIM and self.alpha is None:
            raise ValueError("propensity trimming needs alpha")
        if self.kind is PolicyKind.WEIGHT_TRUNCATION and self.quantile is None:
            raise ValueError("weight truncation needs a quantile")

    @property
    def label(self) -> str:
        if self.kind is PolicyKind.PROPENSITY_TRIM:
            return f"trim_{self.alpha:g}"
        if self.kind is PolicyKind.WEIGHT_TRUNCATION:
            return f"truncate_q{self.quantile:g}"
        return "none"


class TrimmingOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy: TrimmingPolicy
    estimand: Estimand
    population_changed: bool
    n_units: int
    n_dropped: int
    n_dropped_treated: int
    n_dropped_control: int
    estimate: EffectEstimate | None
    error: str | None
    notes: tuple[str, ...]


class TrimmingReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policies_fingerprint: str
    original_estimand_id: str
    propensity_fingerprint: str
    outcomes: tuple[TrimmingOutcome, ...]
    summary: dict[str, JsonValue]


def trimmed_estimand(estimand: Estimand, alpha: float) -> Estimand:
    """Derived estimand for the population restricted to alpha <= e(x) <= 1 - alpha."""
    pop = estimand.target_population
    criterion = f"estimated propensity in [{alpha:g}, {1 - alpha:g}]"
    return estimand.model_copy(
        update={
            "estimand_id": f"{estimand.estimand_id}__trim_{alpha:g}",
            "target_population": TargetPopulation(
                name=f"{pop.name} (propensity-trimmed {alpha:g})",
                description=f"{pop.description}; restricted to units with {criterion}",
                inclusion_criteria=(*pop.inclusion_criteria, criterion),
                exclusion_criteria=pop.exclusion_criteria,
            ),
            "description": f"{estimand.type} on the propensity-trimmed population (not the "
            f"original {estimand.estimand_id})",
        }
    )


def run_trimming_sensitivity(
    data: pd.DataFrame,
    treatment: TreatmentSpec,
    covariates: tuple[CovariateSpec, ...],
    estimand: Estimand,
    estimator: Estimator,
    policies: tuple[TrimmingPolicy, ...],
    *,
    declared_at: datetime,
    run_at: datetime,
    unit_id: str = "unit_id",
    confidence_level: float = 0.95,
) -> TrimmingReport:
    if declared_at > run_at:
        raise ValueError("trimming policies must be declared before they are run")
    if len({p.label for p in policies}) != len(policies):
        raise ValueError("duplicate trimming policies")
    ps = estimate_propensity(data, treatment, covariates, unit_id=unit_id)
    e, t = ps.scores, ps.treated.astype(bool)
    outcomes: list[TrimmingOutcome] = []
    for policy in policies:
        notes: list[str] = []
        target, subset, est = estimand, data, estimator
        keep = np.ones(len(data), dtype=bool)
        if policy.kind is PolicyKind.PROPENSITY_TRIM:
            assert policy.alpha is not None
            keep = (e >= policy.alpha) & (e <= 1 - policy.alpha)
            subset = data.loc[keep]
            target = trimmed_estimand(estimand, policy.alpha)
            notes.append("target population restricted: results refer to the derived estimand")
        elif policy.kind is PolicyKind.WEIGHT_TRUNCATION:
            if not isinstance(estimator, WeightingEstimator):
                raise ValueError("weight truncation requires a weighting estimator")
            est = dataclasses.replace(estimator, truncation_quantile=policy.quantile)
            notes.append(
                "population unchanged; truncated weights bias the estimator for the original "
                "estimand in exchange for lower variance"
            )
        result: EffectEstimate | None = None
        error: str | None = None
        try:
            result = run_estimator(est, subset, target, confidence_level=confidence_level)
        except Exception as exc:  # recorded, never dropped
            error = f"{type(exc).__name__}: {exc}"
        outcomes.append(
            TrimmingOutcome(
                policy=policy,
                estimand=target,
                population_changed=policy.kind is PolicyKind.PROPENSITY_TRIM,
                n_units=int(keep.sum()),
                n_dropped=int((~keep).sum()),
                n_dropped_treated=int((~keep & t).sum()),
                n_dropped_control=int((~keep & ~t).sum()),
                estimate=result,
                error=error,
                notes=tuple(notes),
            )
        )
    done = [o for o in outcomes if o.estimate is not None]
    summary: dict[str, JsonValue] = {
        "n_policies": len(outcomes),
        "n_succeeded": len(done),
        "estimates": {o.policy.label: o.estimate.estimate for o in done if o.estimate},
        "estimand_ids": {o.policy.label: o.estimand.estimand_id for o in outcomes},
    }
    return TrimmingReport(
        policies_fingerprint=content_hash(
            {
                "declared_at": declared_at.isoformat(),
                "policies": [p.model_dump(mode="json") for p in policies],
            }
        ),
        original_estimand_id=estimand.estimand_id,
        propensity_fingerprint=ps.fingerprint,
        outcomes=tuple(outcomes),
        summary=summary,
    )
