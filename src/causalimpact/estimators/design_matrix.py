"""Numeric design matrices from declared pre-treatment covariates.

Shared by every estimator that adjusts for covariates. Only covariates classified
``eligible`` (known pre-treatment, not affected by treatment) are accepted, so no
estimator can adjust for a post-treatment variable through this path.
"""

from __future__ import annotations

import pandas as pd

from causalimpact.domain.variables import (
    CovariateDType,
    CovariateSpec,
    Eligibility,
    MissingnessPolicy,
    classify_covariate,
)


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
