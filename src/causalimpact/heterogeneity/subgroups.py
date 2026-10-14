"""Pre-specified subgroup effects (Task 5.4).

Subgroups are declared in a ``SubgroupPlan`` (timestamped, content-versioned) before
estimation, and only declared subgroups are estimated. Each subgroup result targets the
*same* estimand type and outcome as the overall analysis, restricted to the subgroup's
population (a derived estimand records the restriction). Subgroup-defining variables must
be known pre-treatment: conditioning on a post-treatment variable would break the
comparison.

Uncertainty and multiplicity: each subgroup reports its own interval, p-values are
adjusted across subgroups with the declared correction, and when subgroups are mutually
exclusive a Cochran Q test of effect homogeneity is reported.
"""

from __future__ import annotations

from datetime import datetime
from typing import Self

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, JsonValue, model_validator
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand
from causalimpact.domain.fingerprint import content_hash
from causalimpact.domain.study_design import TargetPopulation
from causalimpact.domain.types import AwareDatetime, NonBlankStr
from causalimpact.domain.variables import CovariateSpec, Eligibility, classify_covariate
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.experiments.decision import CorrectionMethod, adjust_p_values


class SubgroupDefinition(BaseModel):
    """Units whose ``variable`` is in ``values`` or within [lower, upper)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    variable: NonBlankStr
    values: tuple[str | int | float, ...] | None = None
    lower: float | None = None
    upper: float | None = None

    @model_validator(mode="after")
    def _one_rule(self) -> Self:
        has_values = self.values is not None
        has_range = self.lower is not None or self.upper is not None
        if has_values == has_range:
            raise ValueError("define a subgroup by values or by a numeric range, not both")
        if self.lower is not None and self.upper is not None and self.lower >= self.upper:
            raise ValueError("lower must be below upper")
        return self

    def mask(self, data: pd.DataFrame) -> np.ndarray:
        column = data[self.variable]
        if self.values is not None:
            out: np.ndarray = column.isin(self.values).to_numpy()
            return out
        lo = -np.inf if self.lower is None else self.lower
        hi = np.inf if self.upper is None else self.upper
        return ((column >= lo) & (column < hi)).to_numpy()

    def describe(self) -> str:
        if self.values is not None:
            return f"{self.variable} in {list(self.values)}"
        return f"{self.lower} <= {self.variable} < {self.upper}"


class SubgroupPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subgroups: tuple[SubgroupDefinition, ...]
    declared_at: AwareDatetime
    correction: CorrectionMethod = CorrectionMethod.HOLM

    @model_validator(mode="after")
    def _unique(self) -> Self:
        names = [s.name for s in self.subgroups]
        if not names or len(names) != len(set(names)):
            raise ValueError("declare at least one subgroup, with unique names")
        return self

    @property
    def version(self) -> str:
        return content_hash(self.model_dump(mode="json"))


class SubgroupResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    definition: str
    estimand_id: str
    n_units: int
    estimate: EffectEstimate | None
    adjusted_p_value: float | None
    error: str | None


class SubgroupReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan_version: str
    estimand_id: str
    correction: CorrectionMethod
    results: tuple[SubgroupResult, ...]
    homogeneity: dict[str, JsonValue]


def subgroup_estimand(estimand: Estimand, subgroup: SubgroupDefinition) -> Estimand:
    pop = estimand.target_population
    rule = subgroup.describe()
    return estimand.model_copy(
        update={
            "estimand_id": f"{estimand.estimand_id}__sub_{subgroup.name}",
            "target_population": TargetPopulation(
                name=f"{pop.name} / {subgroup.name}",
                description=f"{pop.description}; subgroup {rule}",
                inclusion_criteria=(*pop.inclusion_criteria, rule),
                exclusion_criteria=pop.exclusion_criteria,
            ),
        }
    )


def estimate_subgroups(
    plan: SubgroupPlan,
    data: pd.DataFrame,
    estimand: Estimand,
    estimator: Estimator,
    covariates: tuple[CovariateSpec, ...],
    *,
    run_at: datetime,
    confidence_level: float = 0.95,
) -> SubgroupReport:
    if plan.declared_at > run_at:
        raise ValueError("subgroups must be declared before estimation")
    meta = {c.name: c for c in covariates}
    for sub in plan.subgroups:
        spec = meta.get(sub.variable)
        if spec is None or classify_covariate(spec).eligibility is not Eligibility.ELIGIBLE:
            raise ValueError(
                f"subgroup variable {sub.variable!r} must be declared and known pre-treatment"
            )
    masks = {s.name: s.mask(data) for s in plan.subgroups}
    raw: list[tuple[SubgroupDefinition, Estimand, int, EffectEstimate | None, str | None]] = []
    for sub in plan.subgroups:
        target = subgroup_estimand(estimand, sub)
        subset = data.loc[masks[sub.name]]
        try:
            est = run_estimator(estimator, subset, target, confidence_level=confidence_level)
            raw.append((sub, target, len(subset), est, None))
        except Exception as exc:  # recorded, never dropped
            raw.append((sub, target, len(subset), None, f"{type(exc).__name__}: {exc}"))

    p_values = [r[3].p_value for r in raw if r[3] is not None and r[3].p_value is not None]
    adjusted = iter(adjust_p_values(p_values, plan.correction))
    results = tuple(
        SubgroupResult(
            name=sub.name,
            definition=sub.describe(),
            estimand_id=target.estimand_id,
            n_units=n,
            estimate=est,
            adjusted_p_value=next(adjusted)
            if est is not None and est.p_value is not None
            else None,
            error=err,
        )
        for sub, target, n, est, err in raw
    )
    return SubgroupReport(
        plan_version=plan.version,
        estimand_id=estimand.estimand_id,
        correction=plan.correction,
        results=results,
        homogeneity=_homogeneity(results, masks),
    )


def _homogeneity(
    results: tuple[SubgroupResult, ...], masks: dict[str, np.ndarray]
) -> dict[str, JsonValue]:
    stacked = np.vstack(list(masks.values()))
    disjoint = bool(np.all(stacked.sum(axis=0) <= 1))
    done = [r.estimate for r in results if r.estimate is not None]
    if not disjoint:
        return {"tested": False, "reason": "subgroups overlap; Cochran Q requires disjoint groups"}
    if len(done) < 2:
        return {"tested": False, "reason": "fewer than two estimated subgroups"}
    est = np.array([e.estimate for e in done])
    w = 1.0 / np.array([e.std_error for e in done]) ** 2
    pooled = float(np.sum(w * est) / np.sum(w))
    q = float(np.sum(w * (est - pooled) ** 2))
    df = len(done) - 1
    return {
        "tested": True,
        "cochran_q": q,
        "df": df,
        "p_value": float(stats.chi2.sf(q, df)),
        "inverse_variance_pooled_estimate": pooled,
    }
