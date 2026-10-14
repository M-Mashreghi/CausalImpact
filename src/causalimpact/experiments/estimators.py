"""Unadjusted ITT estimators for randomized experiments (Task 2.4).

Both estimators contrast units *as assigned* and therefore target the ITT estimand only;
they never relabel it as an ATE (which would additionally require full compliance).

* Difference in means (continuous outcomes): Neyman variance s1²/n1 + s0²/n0 with a
  Welch-Satterthwaite t interval.
* Difference in proportions (binary 0/1 outcomes): unpooled Wald variance
  p1(1-p1)/n1 + p0(1-p0)/n0 with a normal interval.

Missing outcomes are refused rather than dropped: deciding how to handle them is an
attrition question (Task 2.10), not an estimator detail.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.variables import TreatmentSpec


@dataclass(frozen=True)
class ArmSamples:
    treated: np.ndarray
    control: np.ndarray


def split_arms(data: pd.DataFrame, estimand: Estimand, treatment: TreatmentSpec) -> ArmSamples:
    """Outcome arrays by assigned arm, enforcing the ITT preconditions."""
    if estimand.treatment != treatment.name:
        raise ValueError(
            f"estimand treatment {estimand.treatment!r} != treatment column {treatment.name!r}"
        )
    for column in (treatment.name, estimand.outcome):
        if column not in data:
            raise ValueError(f"data is missing column {column!r}")
    arm = data[treatment.name]
    outcome = data[estimand.outcome]
    if arm.isna().any():
        raise ValueError("treatment assignment has missing values")
    if unknown := set(arm.unique()) - {treatment.control_value, treatment.treated_value}:
        raise ValueError(f"unexpected treatment values {sorted(map(str, unknown))}")
    if n_missing := int(outcome.isna().sum()):
        raise ValueError(
            f"{n_missing} missing outcomes; resolve via attrition diagnostics before "
            "estimating ITT (missing outcomes are not dropped silently)"
        )
    if not pd.api.types.is_numeric_dtype(outcome) or pd.api.types.is_bool_dtype(outcome):
        raise ValueError("outcome must be numeric")
    treated = outcome[arm == treatment.treated_value].to_numpy(dtype=float)
    control = outcome[arm == treatment.control_value].to_numpy(dtype=float)
    if treated.size < 2 or control.size < 2:
        raise ValueError("each arm needs at least two units")
    return ArmSamples(treated=treated, control=control)


def _check_itt(estimand: Estimand, name: str) -> None:
    if estimand.type is not EstimandType.ITT:
        raise ValueError(f"{name} targets ITT only, not {estimand.type}")


@dataclass(frozen=True)
class DifferenceInMeans:
    treatment: TreatmentSpec
    name: str = "difference_in_means"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ITT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        _check_itt(estimand, self.name)
        arms = split_arms(data, estimand, self.treatment)
        n1, n0 = arms.treated.size, arms.control.size
        v1 = float(arms.treated.var(ddof=1)) / n1
        v0 = float(arms.control.var(ddof=1)) / n0
        effect = float(arms.treated.mean() - arms.control.mean())
        se = math.sqrt(v1 + v0)
        if se == 0.0:
            raise ValueError("zero outcome variance in both arms; uncertainty is undefined")
        df = (v1 + v0) ** 2 / (v1**2 / (n1 - 1) + v0**2 / (n0 - 1))
        crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))
        p_value = float(2 * stats.t.sf(abs(effect) / se, df))
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - crit * se,
            ci_upper=effect + crit * se,
            confidence_level=confidence_level,
            inference_method="neyman_variance_welch_t",
            p_value=p_value,
            degrees_of_freedom=df,
            n_units=n1 + n0,
            n_treated=n1,
            n_control=n0,
        )


@dataclass(frozen=True)
class DifferenceInProportions:
    treatment: TreatmentSpec
    name: str = "difference_in_proportions"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ITT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        _check_itt(estimand, self.name)
        arms = split_arms(data, estimand, self.treatment)
        for sample in (arms.treated, arms.control):
            if not np.isin(sample, (0.0, 1.0)).all():
                raise ValueError("difference in proportions requires a 0/1 outcome")
        n1, n0 = arms.treated.size, arms.control.size
        p1, p0 = float(arms.treated.mean()), float(arms.control.mean())
        se = math.sqrt(p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0)
        if se == 0.0:
            raise ValueError(
                "both arms have proportions of exactly 0 or 1; the Wald interval is "
                "degenerate. Use an exact method instead."
            )
        effect = p1 - p0
        crit = float(stats.norm.ppf(0.5 + confidence_level / 2))
        p_value = float(2 * stats.norm.sf(abs(effect) / se))
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - crit * se,
            ci_upper=effect + crit * se,
            confidence_level=confidence_level,
            inference_method="unpooled_wald_normal",
            p_value=p_value,
            n_units=n1 + n0,
            n_treated=n1,
            n_control=n0,
        )
