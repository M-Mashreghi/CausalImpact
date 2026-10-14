"""Covariate-adjusted ITT estimator for randomized experiments (Task 2.5).

Lin (2013) estimator: OLS of the outcome on the assignment indicator, mean-centred
pre-treatment covariates and their interactions with assignment. With centring, the
assignment coefficient estimates the ITT even when effects vary with covariates.
Adjustment changes precision, not the estimand.

The variance targets the population ITT: the HC2 variance of the assignment coefficient
plus g' S_x g / n, where g are the interaction coefficients and S_x the covariate
covariance. The second term accounts for estimating the covariate means used for
centring; without it intervals under-cover when effects are heterogeneous.

Only covariates known to be pre-treatment and unaffected by treatment are accepted; a
post-treatment adjustment variable could bias the ITT.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.domain.variables import (
    CovariateDType,
    CovariateSpec,
    Eligibility,
    MissingnessPolicy,
    TreatmentSpec,
    classify_covariate,
)
from causalimpact.estimators.ols import ols_hc2
from causalimpact.experiments.estimators import split_arms


def covariate_matrix(data: pd.DataFrame, covariates: tuple[CovariateSpec, ...]) -> pd.DataFrame:
    """Numeric design columns for pre-treatment covariates (categoricals one-hot encoded)."""
    if not covariates:
        raise ValueError("regression adjustment needs at least one covariate")
    refused = [
        c.name for c in covariates if classify_covariate(c).eligibility is not Eligibility.ELIGIBLE
    ]
    if refused:
        raise ValueError(
            "adjustment covariates must be known pre-treatment and not affected by "
            f"treatment; not eligible: {refused}"
        )
    columns: dict[str, pd.Series] = {}
    for cov in covariates:
        if cov.name not in data:
            raise ValueError(f"data is missing covariate {cov.name!r}")
        col = data[cov.name]
        missing = col.isna()
        if missing.any():
            if cov.missingness_policy is not MissingnessPolicy.INDICATOR:
                raise ValueError(
                    f"covariate {cov.name!r} has {int(missing.sum())} missing values; only the "
                    "'indicator' missingness policy is supported for adjustment"
                )
            columns[f"{cov.name}__missing"] = missing.astype(float)
        if cov.dtype is CovariateDType.CATEGORICAL:
            levels = sorted(col.dropna().astype(str).unique())
            for level in levels[1:]:
                columns[f"{cov.name}=={level}"] = (col.astype(str) == level).astype(float)
        else:
            if not pd.api.types.is_numeric_dtype(col):
                raise ValueError(f"covariate {cov.name!r} must be numeric")
            filled = col.astype(float)
            columns[cov.name] = filled.fillna(filled.mean()) if missing.any() else filled
    return pd.DataFrame(columns, index=data.index)


@dataclass(frozen=True)
class RegressionAdjustedITT:
    treatment: TreatmentSpec
    covariates: tuple[CovariateSpec, ...]
    name: str = "lin_regression_adjustment"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ITT})

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if estimand.type is not EstimandType.ITT:
            raise ValueError(f"{self.name} targets ITT only, not {estimand.type}")
        if estimand.outcome in {c.name for c in self.covariates}:
            raise ValueError("the outcome cannot be an adjustment covariate")
        arms = split_arms(data, estimand, self.treatment)  # validates arms and outcome
        x = covariate_matrix(data, self.covariates)
        centred = (x - x.mean()).to_numpy(dtype=float)
        t = (data[self.treatment.name] == self.treatment.treated_value).to_numpy(dtype=float)
        y = data[estimand.outcome].to_numpy(dtype=float)
        design = np.column_stack([np.ones_like(t), t, centred, centred * t[:, None]])
        fit = ols_hc2(design, y)

        effect = float(fit.coef[1])
        n_cov = centred.shape[1]
        interactions = fit.coef[2 + n_cov :]
        covariate_cov = np.atleast_2d(np.cov(centred, rowvar=False, ddof=1))
        mean_sampling_var = float(interactions @ covariate_cov @ interactions) / fit.n
        se = math.sqrt(float(fit.cov[1, 1]) + mean_sampling_var)
        df = fit.df_resid
        crit = float(stats.t.ppf(0.5 + confidence_level / 2, df))
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=effect,
            std_error=se,
            ci_lower=effect - crit * se,
            ci_upper=effect + crit * se,
            confidence_level=confidence_level,
            inference_method="ols_interacted_centred_hc2_plus_covariate_mean_t",
            p_value=float(2 * stats.t.sf(abs(effect) / se, df)),
            degrees_of_freedom=float(df),
            n_units=fit.n,
            n_treated=int(arms.treated.size),
            n_control=int(arms.control.size),
        )
