"""Outcome-regression (g-computation) estimator for ATE / ATT / ATC (Task 3.6).

Nuisance and effect are separate objects:

* an ``OutcomeLearner`` fits mu_a(x) = E[Y | T=a, X=x] separately in each arm and returns a
  fitted predictor (the nuisance);
* ``OutcomeRegressionEstimator`` turns the fitted predictors into an effect:

  - ATE = mean over all units of mu_1(x) - mu_0(x)
  - ATT = mean over treated units of Y - mu_0(x)
  - ATC = mean over control units of mu_1(x) - Y

Regression extrapolates silently where arms do not overlap, so the propensity overlap
diagnostic is computed alongside and attached to the estimate (it is surfaced, not used
to refuse, because this estimator does not divide by the propensity).

Uncertainty: seeded nonparametric bootstrap of the whole pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.design_matrix import covariate_matrix
from causalimpact.observational.overlap import check_overlap
from causalimpact.observational.propensity import estimate_propensity


class FittedOutcomeModel(Protocol):
    def predict(self, x: np.ndarray) -> np.ndarray: ...


class OutcomeLearner(Protocol):
    @property
    def name(self) -> str: ...

    def config(self) -> dict[str, JsonValue]: ...

    def fit(self, x: np.ndarray, y: np.ndarray) -> FittedOutcomeModel: ...


@dataclass(frozen=True)
class FittedLinear:
    coef: np.ndarray

    def predict(self, x: np.ndarray) -> np.ndarray:
        out: np.ndarray = np.column_stack([np.ones(len(x)), x]) @ self.coef
        return out


@dataclass(frozen=True)
class LinearOutcomeModel:
    name: str = "ols_linear"

    def config(self) -> dict[str, JsonValue]:
        return {"model": self.name}

    def fit(self, x: np.ndarray, y: np.ndarray) -> FittedLinear:
        design = np.column_stack([np.ones(len(x)), x])
        if len(design) <= design.shape[1]:
            raise ValueError("too few units in an arm to fit the outcome model")
        if np.linalg.matrix_rank(design) < design.shape[1]:
            raise ValueError("outcome design matrix is rank deficient within an arm")
        coef, *_ = np.linalg.lstsq(design, y, rcond=None)
        return FittedLinear(coef=coef)


@dataclass(frozen=True)
class OutcomeNuisance:
    """Fitted arm-specific outcome models; contains no causal contrast."""

    treated_model: FittedOutcomeModel
    control_model: FittedOutcomeModel
    learner_config: dict[str, JsonValue]

    def mu1(self, x: np.ndarray) -> np.ndarray:
        return self.treated_model.predict(x)

    def mu0(self, x: np.ndarray) -> np.ndarray:
        return self.control_model.predict(x)


def fit_outcome_nuisance(
    learner: OutcomeLearner, x: np.ndarray, y: np.ndarray, treated: np.ndarray
) -> OutcomeNuisance:
    t = treated.astype(bool)
    return OutcomeNuisance(
        treated_model=learner.fit(x[t], y[t]),
        control_model=learner.fit(x[~t], y[~t]),
        learner_config=learner.config(),
    )


def g_computation(
    nuisance: OutcomeNuisance, x: np.ndarray, y: np.ndarray, treated: np.ndarray, kind: EstimandType
) -> float:
    t = treated.astype(bool)
    if kind is EstimandType.ATE:
        return float(np.mean(nuisance.mu1(x) - nuisance.mu0(x)))
    if kind is EstimandType.ATT:
        return float(np.mean(y[t] - nuisance.mu0(x[t])))
    if kind is EstimandType.ATC:
        return float(np.mean(nuisance.mu1(x[~t]) - y[~t]))
    raise ValueError(f"outcome regression does not target {kind}")


@dataclass(frozen=True)
class OutcomeRegressionEstimator:
    treatment: TreatmentSpec
    covariates: tuple[CovariateSpec, ...]
    seed: int
    learner: OutcomeLearner = field(default_factory=LinearOutcomeModel)
    n_bootstrap: int = 500
    unit_id: str = "unit_id"
    name: str = "outcome_regression_g_computation"
    supported_estimands: frozenset[EstimandType] = frozenset(
        {EstimandType.ATE, EstimandType.ATT, EstimandType.ATC}
    )

    def _arrays(self, data: pd.DataFrame, outcome: str) -> tuple[np.ndarray, ...]:
        arm = data[self.treatment.name]
        if (
            arm.isna().any()
            or not arm.isin([self.treatment.control_value, self.treatment.treated_value]).all()
        ):
            raise ValueError("treatment must be non-missing and use the declared levels")
        if data[outcome].isna().any():
            raise ValueError("missing outcomes must be handled before outcome regression")
        x = covariate_matrix(data, self.covariates).to_numpy(dtype=float)
        y = data[outcome].to_numpy(dtype=float)
        t = (arm == self.treatment.treated_value).to_numpy(dtype=float)
        return x, y, t

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if estimand.type not in self.supported_estimands:
            raise ValueError(f"{self.name} does not target {estimand.type}")
        if estimand.treatment != self.treatment.name:
            raise ValueError("estimand treatment differs from the treatment column")
        x, y, t = self._arrays(data, estimand.outcome)
        nuisance = fit_outcome_nuisance(self.learner, x, y, t)
        effect = g_computation(nuisance, x, y, t, estimand.type)

        rng = np.random.default_rng(derive_seed(self.seed, "outcome_regression_bootstrap"))
        n = len(y)
        replicates = []
        for _ in range(self.n_bootstrap):
            idx = rng.integers(0, n, n)
            boot = fit_outcome_nuisance(self.learner, x[idx], y[idx], t[idx])
            replicates.append(g_computation(boot, x[idx], y[idx], t[idx], estimand.type))
        se = float(np.std(replicates, ddof=1))
        z = float(stats.norm.ppf(0.5 + confidence_level / 2))

        ps = estimate_propensity(data, self.treatment, self.covariates, unit_id=self.unit_id)
        overlap = check_overlap(ps, estimand.type)
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
            n_control=int(n - t.sum()),
            details={
                "outcome_learner": nuisance.learner_config,
                "covariates": [c.name for c in self.covariates],
                "n_bootstrap": self.n_bootstrap,
                "seed": self.seed,
                "overlap_status": overlap.status.value,
                "overlap_findings": [f.model_dump(mode="json") for f in overlap.findings],
            },
        )
