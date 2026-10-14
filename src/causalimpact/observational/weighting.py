"""Inverse-probability, stabilized and overlap weighting (Task 3.5).

Every scheme maps to exactly one estimand; the mapping is explicit and enforced:

=================  ===========================================  ========
scheme             weights (treated / control)                  estimand
=================  ===========================================  ========
``ipw``            1/e        /  1/(1-e)                        ATE
``stabilized``     P(T=1)/e   /  P(T=0)/(1-e)                   ATE
``att``            1          /  e/(1-e)                        ATT
``atc``            (1-e)/e    /  1                              ATC
``overlap``        1-e        /  e                              ATO
=================  ===========================================  ========

The effect is the difference of weighted (Hajek) means: within each arm the weights are
normalised to sum to one. Overlap weights target the *overlap population* (ATO), which
is a different estimand from the ATE and is labelled as such.

Uncertainty: nonparametric bootstrap of the whole pipeline (propensity re-estimated in
every replicate) with a seed derived from the run seed, so the propensity estimation
step is reflected in the standard error and results are reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.observational.overlap import (
    OverlapPolicy,
    check_overlap,
    ensure_overlap,
    kish_ess,
)
from causalimpact.observational.propensity import (
    LogisticPropensity,
    PropensityModel,
    estimate_propensity,
)


class WeightScheme(StrEnum):
    IPW = "ipw"
    STABILIZED = "stabilized"
    ATT = "att"
    ATC = "atc"
    OVERLAP = "overlap"


SCHEME_ESTIMAND: dict[WeightScheme, EstimandType] = {
    WeightScheme.IPW: EstimandType.ATE,
    WeightScheme.STABILIZED: EstimandType.ATE,
    WeightScheme.ATT: EstimandType.ATT,
    WeightScheme.ATC: EstimandType.ATC,
    WeightScheme.OVERLAP: EstimandType.ATO,
}


def compute_weights(scheme: WeightScheme, e: np.ndarray, treated: np.ndarray) -> np.ndarray:
    t = np.asarray(treated, dtype=bool)
    if np.any((e <= 0) | (e >= 1)):
        raise ValueError("propensity scores must lie strictly inside (0, 1)")
    if scheme is WeightScheme.IPW:
        w = np.where(t, 1 / e, 1 / (1 - e))
    elif scheme is WeightScheme.STABILIZED:
        p1 = t.mean()
        w = np.where(t, p1 / e, (1 - p1) / (1 - e))
    elif scheme is WeightScheme.ATT:
        w = np.where(t, 1.0, e / (1 - e))
    elif scheme is WeightScheme.ATC:
        w = np.where(t, (1 - e) / e, 1.0)
    else:
        w = np.where(t, 1 - e, e)
    out: np.ndarray = w.astype(float)
    return out


def normalized_weights(weights: np.ndarray, treated: np.ndarray) -> np.ndarray:
    """Weights rescaled to sum to one within each arm (Hajek normalisation)."""
    t = np.asarray(treated, dtype=bool)
    out = np.empty_like(weights, dtype=float)
    out[t] = weights[t] / weights[t].sum()
    out[~t] = weights[~t] / weights[~t].sum()
    return out


def hajek_effect(y: np.ndarray, weights: np.ndarray, treated: np.ndarray) -> float:
    t = np.asarray(treated, dtype=bool)
    w = normalized_weights(weights, t)
    return float(np.dot(w[t], y[t]) - np.dot(w[~t], y[~t]))


def weight_diagnostics(
    weights: np.ndarray,
    treated: np.ndarray,
    scheme: WeightScheme,
    *,
    max_unit_share: float = 0.05,
    max_ratio_to_mean: float = 20.0,
) -> DiagnosticResult:
    """Weight distribution, ESS and extreme-weight flags (per arm)."""
    t = np.asarray(treated, dtype=bool)
    findings: list[Finding] = []
    per_arm: dict[str, JsonValue] = {}
    for label, mask in (("treated", t), ("control", ~t)):
        w = weights[mask]
        share = w / w.sum()
        ratio = w / w.mean()
        n_extreme = int(np.sum((share > max_unit_share) | (ratio > max_ratio_to_mean)))
        per_arm[label] = {
            "n": int(w.size),
            "sum": float(w.sum()),
            "mean": float(w.mean()),
            "min": float(w.min()),
            "max": float(w.max()),
            "quantiles": {f"{q:g}": float(np.quantile(w, q)) for q in (0.5, 0.9, 0.99)},
            "coefficient_of_variation": float(w.std() / w.mean()),
            "effective_sample_size": kish_ess(w),
            "max_unit_share": float(share.max()),
            "n_extreme": n_extreme,
        }
        if n_extreme:
            findings.append(
                Finding(
                    code="extreme_weights",
                    severity=FindingSeverity.WARNING,
                    message=(
                        f"{n_extreme} {label} units carry extreme weight (> {max_unit_share:.0%} "
                        f"of the arm or > {max_ratio_to_mean:g}x the mean); the estimate "
                        "depends heavily on few units"
                    ),
                    count=n_extreme,
                )
            )
    metrics: dict[str, JsonValue] = {
        "scheme": scheme.value,
        "estimand": SCHEME_ESTIMAND[scheme].value,
        "thresholds": {"max_unit_share": max_unit_share, "max_ratio_to_mean": max_ratio_to_mean},
        **per_arm,
    }
    return DiagnosticResult(name="weights", findings=tuple(findings), metrics=metrics)


@dataclass(frozen=True)
class WeightingEstimator:
    treatment: TreatmentSpec
    covariates: tuple[CovariateSpec, ...]
    scheme: WeightScheme
    seed: int
    n_bootstrap: int = 500
    propensity_model: PropensityModel = field(default_factory=LogisticPropensity)
    overlap_policy: OverlapPolicy = field(default_factory=OverlapPolicy)
    unit_id: str = "unit_id"

    @property
    def name(self) -> str:
        return f"hajek_weighting_{self.scheme.value}"

    @property
    def supported_estimands(self) -> frozenset[EstimandType]:
        return frozenset({SCHEME_ESTIMAND[self.scheme]})

    def _point(self, data: pd.DataFrame, outcome: str) -> tuple[float, np.ndarray, np.ndarray]:
        ps = estimate_propensity(
            data, self.treatment, self.covariates, model=self.propensity_model, unit_id=self.unit_id
        )
        w = compute_weights(self.scheme, ps.scores, ps.treated)
        y = data[outcome].to_numpy(dtype=float)
        return hajek_effect(y, w, ps.treated), w, ps.scores

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if estimand.type is not SCHEME_ESTIMAND[self.scheme]:
            raise ValueError(f"{self.scheme} weights target {SCHEME_ESTIMAND[self.scheme]}")
        if estimand.treatment != self.treatment.name:
            raise ValueError("estimand treatment differs from the treatment column")
        if data[estimand.outcome].isna().any():
            raise ValueError("missing outcomes must be handled before weighting")
        if self.n_bootstrap < 50:
            raise ValueError("n_bootstrap must be at least 50")

        ps = estimate_propensity(
            data, self.treatment, self.covariates, model=self.propensity_model, unit_id=self.unit_id
        )
        if self.scheme is not WeightScheme.OVERLAP:  # overlap weights are bounded by design
            overlap = check_overlap(ps, estimand.type, self.overlap_policy)
            ensure_overlap(overlap)
        effect, weights, _ = self._point(data, estimand.outcome)

        rng = np.random.default_rng(derive_seed(self.seed, "weighting_bootstrap"))
        n = len(data)
        replicates: list[float] = []
        failures = 0
        for _ in range(self.n_bootstrap):
            sample = data.iloc[rng.integers(0, n, n)].reset_index(drop=True)
            sample[self.unit_id] = np.arange(n)  # resampled rows need unique ids
            try:
                replicates.append(self._point(sample, estimand.outcome)[0])
            except (ValueError, RuntimeError):
                failures += 1
        if failures > 0.05 * self.n_bootstrap:
            raise RuntimeError(f"{failures} bootstrap replicates failed; uncertainty unreliable")
        se = float(np.std(replicates, ddof=1))
        z = float(stats.norm.ppf(0.5 + confidence_level / 2))
        t = ps.treated.astype(bool)
        diag = weight_diagnostics(weights, t, self.scheme)
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - z * se,
            ci_upper=effect + z * se,
            confidence_level=confidence_level,
            inference_method="nonparametric_bootstrap_se_normal_ci",
            p_value=float(2 * stats.norm.sf(abs(effect) / se)) if se > 0 else None,
            n_units=n,
            n_treated=int(t.sum()),
            n_control=int((~t).sum()),
            details={
                "scheme": self.scheme.value,
                "propensity_fingerprint": ps.fingerprint,
                "propensity_config": ps.nuisance_config,
                "n_bootstrap": self.n_bootstrap,
                "bootstrap_failures": failures,
                "seed": self.seed,
                "weights": diag.metrics,
                "weight_findings": [f.model_dump(mode="json") for f in diag.findings],
            },
        )
