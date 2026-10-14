"""Doubly robust AIPW estimator for the ATE and ATT (Task 3.7).

ATE uncentred influence values (Robins, Rotnitzky & Zhao 1994):

    psi_i = mu1(x) - mu0(x) + t (y - mu1(x)) / e(x) - (1 - t)(y - mu0(x)) / (1 - e(x))

tau = mean(psi), SE = sd(psi) / sqrt(n).

ATT (Hahn 1998 / Mercatanti & Li 2014 form), with p = mean(t):

    tau = sum_i [t (y - mu0) - (1 - t) e/(1 - e) (y - mu0)] / sum_i t
    phi_i = [t (y - mu0 - tau) - (1 - t) e/(1 - e) (y - mu0)] / p,  SE = sd(phi) / sqrt(n)

The estimator is consistent if *either* the outcome model or the propensity model is
correctly specified. Nuisances here are fitted in-sample, which is valid for the
low-complexity parametric learners provided; flexible ML learners require the
cross-fitted engine (Task 3.8). Overlap is checked first and blocking overlap refuses.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.design_matrix import covariate_matrix
from causalimpact.observational.outcome_regression import (
    LinearOutcomeModel,
    OutcomeLearner,
    OutcomeNuisance,
    fit_outcome_nuisance,
)
from causalimpact.observational.overlap import OverlapPolicy, check_overlap, ensure_overlap
from causalimpact.observational.propensity import (
    LogisticPropensity,
    PropensityModel,
    estimate_propensity,
)


def aipw_scores(
    kind: EstimandType,
    y: np.ndarray,
    t: np.ndarray,
    e: np.ndarray,
    mu1: np.ndarray,
    mu0: np.ndarray,
) -> tuple[float, np.ndarray]:
    """Point estimate and mean-zero influence values for ``kind`` (ATE or ATT)."""
    if kind is EstimandType.ATE:
        psi = mu1 - mu0 + t * (y - mu1) / e - (1 - t) * (y - mu0) / (1 - e)
        tau = float(psi.mean())
        return tau, psi - tau
    if kind is EstimandType.ATT:
        p = float(t.mean())
        resid0 = y - mu0
        odds = e / (1 - e)
        tau = float(np.sum(t * resid0 - (1 - t) * odds * resid0) / np.sum(t))
        phi = (t * (resid0 - tau) - (1 - t) * odds * resid0) / p
        return tau, phi
    raise ValueError(f"AIPW supports ATE and ATT, not {kind}")


@dataclass(frozen=True)
class AIPWEstimator:
    treatment: TreatmentSpec
    covariates: tuple[CovariateSpec, ...]
    outcome_learner: OutcomeLearner = field(default_factory=LinearOutcomeModel)
    propensity_model: PropensityModel = field(default_factory=LogisticPropensity)
    overlap_policy: OverlapPolicy = field(default_factory=OverlapPolicy)
    unit_id: str = "unit_id"
    name: str = "aipw"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ATE, EstimandType.ATT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if estimand.type not in self.supported_estimands:
            raise ValueError(f"AIPW does not target {estimand.type}")
        if estimand.treatment != self.treatment.name:
            raise ValueError("estimand treatment differs from the treatment column")
        if data[estimand.outcome].isna().any():
            raise ValueError("missing outcomes must be handled before AIPW")

        ps = estimate_propensity(
            data, self.treatment, self.covariates, model=self.propensity_model, unit_id=self.unit_id
        )
        ensure_overlap(check_overlap(ps, estimand.type, self.overlap_policy))
        x = covariate_matrix(data, self.covariates).to_numpy(dtype=float)
        y = data[estimand.outcome].to_numpy(dtype=float)
        t = ps.treated
        nuisance: OutcomeNuisance = fit_outcome_nuisance(self.outcome_learner, x, y, t)
        tau, influence = aipw_scores(
            estimand.type, y, t, ps.scores, nuisance.mu1(x), nuisance.mu0(x)
        )
        n = len(y)
        se = float(np.sqrt(np.mean(influence**2) / n))
        crit = float(stats.norm.ppf(0.5 + confidence_level / 2))
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=tau,
            std_error=se,
            ci_lower=tau - crit * se,
            ci_upper=tau + crit * se,
            confidence_level=confidence_level,
            inference_method="influence_function_normal",
            p_value=float(2 * stats.norm.sf(abs(tau) / se)) if se > 0 else None,
            n_units=n,
            n_treated=int(t.sum()),
            n_control=int(n - t.sum()),
            details={
                "propensity_config": ps.nuisance_config,
                "propensity_fingerprint": ps.fingerprint,
                "outcome_learner": nuisance.learner_config,
                "cross_fitting": False,
                "nuisance_note": "in-sample nuisance fits; valid for low-complexity "
                "parametric learners. Use cross-fitting for flexible ML learners.",
            },
        )
