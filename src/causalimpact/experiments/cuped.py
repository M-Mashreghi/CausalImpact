"""CUPED variance reduction with a pre-period metric (Task 2.6).

Deng et al. (2013): Y_cv = Y - theta * (X - mean(X)) with theta = cov(Y, X) / var(X),
estimated on the pooled sample (both arms), then the difference in means of Y_cv. Because
X is a pre-treatment variable whose mean is (in expectation) equal across arms, the
adjusted contrast still estimates the ITT; only its variance changes.

The pre-period metric must be declared pre-treatment and not affected by treatment. If
it is not, adjustment can introduce bias, so it is refused rather than warned about.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.variables import (
    CovariateDType,
    CovariateSpec,
    Eligibility,
    TreatmentSpec,
    classify_covariate,
)
from causalimpact.experiments.estimators import DifferenceInMeans

ADJUSTED_SUFFIX = "__cuped"


def cuped_theta(outcome: np.ndarray, pre_metric: np.ndarray) -> float:
    var_x = float(np.var(pre_metric, ddof=1))
    if var_x == 0.0:
        raise ValueError("pre-period metric is constant; CUPED cannot reduce variance")
    return float(np.cov(outcome, pre_metric, ddof=1)[0, 1]) / var_x


@dataclass(frozen=True)
class CupedITT:
    treatment: TreatmentSpec
    pre_metric: CovariateSpec
    name: str = "cuped_difference_in_means"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ITT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        decision = classify_covariate(self.pre_metric)
        if decision.eligibility is not Eligibility.ELIGIBLE:
            raise ValueError(
                f"CUPED covariate {self.pre_metric.name!r} must be known pre-treatment and "
                f"not affected by treatment ({'; '.join(decision.reasons)})"
            )
        if self.pre_metric.dtype is CovariateDType.CATEGORICAL:
            raise ValueError("CUPED needs a numeric or binary pre-period metric")
        if self.pre_metric.name == estimand.outcome:
            raise ValueError("the pre-period metric must be a different column from the outcome")
        if self.pre_metric.name not in data:
            raise ValueError(f"data is missing {self.pre_metric.name!r}")
        x_col = data[self.pre_metric.name]
        if x_col.isna().any():
            raise ValueError("pre-period metric has missing values")

        # Plain difference in means first: validates arms/outcomes and gives the baseline.
        unadjusted = DifferenceInMeans(self.treatment).estimate(
            data, estimand, confidence_level=confidence_level
        )
        y = data[estimand.outcome].to_numpy(dtype=float)
        x = x_col.to_numpy(dtype=float)
        theta = cuped_theta(y, x)
        adjusted_name = estimand.outcome + ADJUSTED_SUFFIX
        adjusted = data.assign(**{adjusted_name: y - theta * (x - x.mean())})
        adjusted_estimand = estimand.model_copy(update={"outcome": adjusted_name})
        out = DifferenceInMeans(self.treatment).estimate(
            adjusted, adjusted_estimand, confidence_level=confidence_level
        )
        variance_ratio = (out.std_error / unadjusted.std_error) ** 2
        return out.model_copy(
            update={
                "estimator": self.name,
                "inference_method": "cuped_pooled_theta_welch_t",
                "details": {
                    "pre_metric": self.pre_metric.name,
                    "theta": theta,
                    "unadjusted_std_error": unadjusted.std_error,
                    "variance_ratio_vs_unadjusted": variance_ratio,
                    "correlation_outcome_pre_metric": float(np.corrcoef(y, x)[0, 1]),
                },
            }
        )
