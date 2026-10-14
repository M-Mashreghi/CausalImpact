"""Propensity-score matching for the ATT, with matched-sample diagnostics (Task 3.4).

Strategy: each treated unit is matched to its ``k`` nearest controls on the logit of the
propensity score, *with replacement*, within a caliper (default 0.2 standard deviations of
the logit score, Austin 2011). Matching with replacement makes the result independent of
the processing order; ties are broken by the controls' input order.

Treated units with no control inside the caliper are dropped. That changes the population
the ATT refers to, so it is reported explicitly (never silently): the estimand becomes the
ATT among *matched* treated units.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from causalimpact.diagnostics.balance import BalanceRow, summarize_balance, weighted_balance_rows
from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.variables import CovariateSpec
from causalimpact.observational.propensity import PropensityScores

NAME = "matching"


class MatchingConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    k: int = Field(default=1, ge=1)
    caliper_sd: float | None = Field(default=0.2, gt=0.0)
    replace: bool = True

    @property
    def method(self) -> str:
        return f"nearest_neighbour_logit_ps_1:{self.k}_with_replacement"


@dataclass(frozen=True)
class MatchResult:
    pairs: pd.DataFrame  # treated_id, control_id, distance
    unmatched_treated: np.ndarray
    caliper: float | None
    config: MatchingConfig
    unit_weights: pd.Series  # matched-sample weight per unit id (treated 1, controls k-share)

    @property
    def n_matched_treated(self) -> int:
        return int(self.pairs["treated_id"].nunique())

    @property
    def n_unique_controls(self) -> int:
        return int(self.pairs["control_id"].nunique())


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-12, 1 - 1e-12)
    logit: np.ndarray = np.log(p / (1 - p))
    return logit


def match_on_propensity(
    propensity: PropensityScores, config: MatchingConfig | None = None
) -> MatchResult:
    config = config or MatchingConfig()
    if not config.replace:
        raise ValueError("only matching with replacement is supported (order-independent)")
    ids = np.asarray(propensity.unit_ids)
    if len(set(ids.tolist())) != ids.size:
        raise ValueError("unit ids must be unique")
    t = np.asarray(propensity.treated, dtype=bool)
    score = _logit(np.asarray(propensity.scores, dtype=float))
    treated_idx, control_idx = np.flatnonzero(t), np.flatnonzero(~t)
    if control_idx.size < config.k:
        raise ValueError(f"need at least k={config.k} controls")
    caliper = None if config.caliper_sd is None else config.caliper_sd * float(np.std(score))

    rows: list[tuple[object, object, float]] = []
    unmatched: list[object] = []
    control_scores = score[control_idx]
    for i in treated_idx:
        distance = np.abs(control_scores - score[i])
        order = np.lexsort((np.arange(distance.size), distance))[: config.k]
        chosen = [j for j in order if caliper is None or distance[j] <= caliper]
        if len(chosen) < config.k:
            unmatched.append(ids[i])
            continue
        rows.extend((ids[i], ids[control_idx[j]], float(distance[j])) for j in chosen)

    pairs = pd.DataFrame(rows, columns=["treated_id", "control_id", "distance"])
    weights = pd.Series(0.0, index=pd.Index(ids, name="unit_id"))
    weights.loc[pairs["treated_id"].unique()] = 1.0
    if len(pairs):
        control_use = pairs.groupby("control_id").size() / config.k
        weights.loc[control_use.index] += control_use.to_numpy()
    return MatchResult(
        pairs=pairs,
        unmatched_treated=np.asarray(unmatched),
        caliper=caliper,
        config=config,
        unit_weights=weights,
    )


def matched_sample_diagnostics(
    match: MatchResult,
    data: pd.DataFrame,
    treated: np.ndarray,
    covariates: tuple[CovariateSpec, ...],
    *,
    unit_id: str = "unit_id",
    smd_threshold: float = 0.1,
) -> DiagnosticResult:
    """Matched counts, distance quality and before/after balance."""
    frame = data.set_index(unit_id)
    weights = match.unit_weights.reindex(frame.index).to_numpy()
    t = np.asarray(treated, dtype=bool)
    before = weighted_balance_rows(frame, t, np.ones(len(frame)), covariates, "before matching")
    after = weighted_balance_rows(frame, t, weights, covariates, "after matching")
    balance = summarize_balance(
        NAME,
        after,
        threshold=smd_threshold,
        imbalance_message=f"post-match |SMD| > {smd_threshold:g}; matching did not achieve "
        "balance on these covariates",
    )
    findings = list(balance.findings)
    n_treated = int(t.sum())
    if match.unmatched_treated.size:
        findings.append(
            Finding(
                code="treated_units_dropped",
                severity=FindingSeverity.WARNING,
                message=(
                    f"{match.unmatched_treated.size} of {n_treated} treated units have no control "
                    "within the caliper and were dropped: the estimand is now the ATT among "
                    "matched treated units, not all treated units"
                ),
                count=int(match.unmatched_treated.size),
            )
        )
    distances = match.pairs["distance"]
    metrics: dict[str, JsonValue] = {
        "method": match.config.method,
        "caliper_logit": match.caliper,
        "n_treated": n_treated,
        "n_matched_treated": match.n_matched_treated,
        "n_unmatched_treated": int(match.unmatched_treated.size),
        "n_unique_controls_used": match.n_unique_controls,
        "max_control_reuse": int(match.pairs["control_id"].value_counts().max())
        if len(match.pairs)
        else 0,
        "mean_distance": float(distances.mean()) if len(distances) else None,
        "max_distance": float(distances.max()) if len(distances) else None,
        "target_population": "matched treated units"
        if match.unmatched_treated.size
        else "all treated units",
        "balance_before": [r.model_dump(mode="json") for r in before],
        "balance_after": [r.model_dump(mode="json") for r in after],
        "max_abs_smd_before": _max_abs(before),
        "max_abs_smd_after": _max_abs(after),
    }
    return DiagnosticResult(name=NAME, findings=tuple(findings), metrics=metrics)


def _max_abs(rows: list[BalanceRow]) -> float | None:
    values = [abs(r.smd) for r in rows if r.smd is not None]
    return max(values) if values else None
