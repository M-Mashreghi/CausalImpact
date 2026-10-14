"""Exploratory heterogeneity search with guardrails (Task 5.5).

Searching many subgroups and reporting the most striking ones overstates heterogeneity
(selection on noise). This module keeps exploratory findings visibly separate from
confirmatory ones:

* ``confirmatory``: only results of a pre-declared ``SubgroupPlan`` (Task 5.4);
* ``exploratory_holdout_validated``: a subgroup *selected* on a discovery split and
  *re-estimated* on an untouched holdout split, with multiplicity adjustment over the
  selected subgroups. Still exploratory: it motivates a confirmatory study;
* ``exploratory_unvalidated``: selected and estimated on the same data. Hypothesis-
  generating only; its estimate is biased by the selection.

Discovery-split estimates are never reported as evidence. The split is seeded.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from causalimpact.domain.estimands import EffectEstimate, Estimand
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.domain.variables import (
    CovariateDType,
    CovariateSpec,
    Eligibility,
    classify_covariate,
)
from causalimpact.estimators.base import Estimator, run_estimator
from causalimpact.experiments.decision import CorrectionMethod, adjust_p_values
from causalimpact.heterogeneity.subgroups import (
    EvidenceLabel,
    SubgroupDefinition,
    subgroup_estimand,
)


class ExplorationConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = Field(ge=0)
    holdout_fraction: float = Field(default=0.5, ge=0.0, lt=1.0)
    top_k: int = Field(default=3, ge=1)
    min_subgroup_size: int = Field(default=30, ge=4)
    correction: CorrectionMethod = CorrectionMethod.HOLM


class ExploratoryFinding(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    subgroup: str
    definition: str
    label: EvidenceLabel
    selection_score: float
    discovery_estimate: float
    reported_estimate: EffectEstimate | None
    adjusted_p_value: float | None
    note: str


class ExploratoryReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    estimand_id: str
    config: ExplorationConfig
    n_candidates: int
    n_discovery: int
    n_holdout: int
    findings: tuple[ExploratoryFinding, ...]
    notes: tuple[str, ...]


def candidate_subgroups(
    data: pd.DataFrame, covariates: tuple[CovariateSpec, ...]
) -> list[SubgroupDefinition]:
    """Levels of categorical/binary covariates and median splits of numeric ones."""
    out: list[SubgroupDefinition] = []
    for cov in covariates:
        if classify_covariate(cov).eligibility is not Eligibility.ELIGIBLE:
            raise ValueError(f"exploration variable {cov.name!r} must be known pre-treatment")
        column = data[cov.name]
        if cov.dtype is CovariateDType.NUMERIC:
            median = float(column.median())
            out.append(
                SubgroupDefinition(name=f"{cov.name}<median", variable=cov.name, upper=median)
            )
            out.append(
                SubgroupDefinition(name=f"{cov.name}>=median", variable=cov.name, lower=median)
            )
        else:
            for level in sorted(column.dropna().unique().tolist(), key=str):
                out.append(
                    SubgroupDefinition(
                        name=f"{cov.name}={level}", variable=cov.name, values=(level,)
                    )
                )
    return out


def explore_subgroups(
    data: pd.DataFrame,
    estimand: Estimand,
    estimator: Estimator,
    covariates: tuple[CovariateSpec, ...],
    config: ExplorationConfig,
) -> ExploratoryReport:
    rng = np.random.default_rng(derive_seed(config.seed, "exploratory_split"))
    holdout = rng.random(len(data)) < config.holdout_fraction
    discovery_data, holdout_data = data.loc[~holdout], data.loc[holdout]
    validated = config.holdout_fraction > 0

    candidates = candidate_subgroups(data, covariates)
    overall = run_estimator(estimator, discovery_data, estimand).estimate
    scored: list[tuple[float, SubgroupDefinition, float]] = []
    for sub in candidates:
        part = discovery_data.loc[sub.mask(discovery_data)]
        if len(part) < config.min_subgroup_size:
            continue
        try:
            est = run_estimator(estimator, part, subgroup_estimand(estimand, sub))
        except Exception:  # an unestimable candidate simply cannot be selected
            continue
        score = abs(est.estimate - overall) / est.std_error
        scored.append((score, sub, est.estimate))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    selected = scored[: config.top_k]

    reported: list[EffectEstimate | None] = []
    for _, sub, _ in selected:
        source = holdout_data if validated else discovery_data
        part = source.loc[sub.mask(source)]
        try:
            reported.append(run_estimator(estimator, part, subgroup_estimand(estimand, sub)))
        except Exception:
            reported.append(None)
    p_values = [r.p_value for r in reported if r is not None and r.p_value is not None]
    adjusted = iter(adjust_p_values(p_values, config.correction))

    label = (
        EvidenceLabel.EXPLORATORY_HOLDOUT_VALIDATED
        if validated
        else EvidenceLabel.EXPLORATORY_UNVALIDATED
    )
    note = (
        "selected on the discovery split, estimated on the untouched holdout; still "
        "exploratory, confirm with a pre-specified analysis"
        if validated
        else "selected and estimated on the same data: hypothesis-generating only, the "
        "estimate is biased by selection"
    )
    findings = tuple(
        ExploratoryFinding(
            subgroup=sub.name,
            definition=sub.describe(),
            label=label,
            selection_score=float(score),
            discovery_estimate=float(disc),
            reported_estimate=rep,
            adjusted_p_value=next(adjusted)
            if rep is not None and rep.p_value is not None
            else None,
            note=note,
        )
        for (score, sub, disc), rep in zip(selected, reported, strict=True)
    )
    return ExploratoryReport(
        estimand_id=estimand.estimand_id,
        config=config,
        n_candidates=len(candidates),
        n_discovery=int((~holdout).sum()),
        n_holdout=int(holdout.sum()),
        findings=findings,
        notes=(
            f"{len(candidates)} candidate subgroups searched; top {config.top_k} selected by "
            "standardized deviation from the overall discovery estimate",
            "exploratory results are never labelled confirmatory",
        ),
    )


def evidence_summary(report: ExploratoryReport) -> dict[str, JsonValue]:
    return {f.subgroup: f.label.value for f in report.findings}
