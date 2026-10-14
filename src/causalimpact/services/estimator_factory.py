"""Typed, whitelisted estimator configurations for API and UI callers.

External callers never construct arbitrary Python objects: they send one of these
configurations, which the service turns into an estimator. Adding an estimator to the
API means adding a configuration here.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.base import Estimator
from causalimpact.experiments.cuped import CupedITT
from causalimpact.experiments.estimators import DifferenceInMeans, DifferenceInProportions
from causalimpact.experiments.regression import RegressionAdjustedITT
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.observational.outcome_regression import OutcomeRegressionEstimator
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme


class _Base(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    treatment: TreatmentSpec


class DifferenceInMeansConfig(_Base):
    kind: Literal["difference_in_means"] = "difference_in_means"


class DifferenceInProportionsConfig(_Base):
    kind: Literal["difference_in_proportions"] = "difference_in_proportions"


class RegressionAdjustedConfig(_Base):
    kind: Literal["regression_adjusted"] = "regression_adjusted"
    covariates: tuple[CovariateSpec, ...]


class CupedConfig(_Base):
    kind: Literal["cuped"] = "cuped"
    pre_metric: CovariateSpec


class AIPWConfig(_Base):
    kind: Literal["aipw"] = "aipw"
    covariates: tuple[CovariateSpec, ...]


class WeightingConfig(_Base):
    kind: Literal["weighting"] = "weighting"
    covariates: tuple[CovariateSpec, ...]
    scheme: WeightScheme
    n_bootstrap: int = Field(default=500, ge=50, le=5000)


class OutcomeRegressionConfig(_Base):
    kind: Literal["outcome_regression"] = "outcome_regression"
    covariates: tuple[CovariateSpec, ...]
    n_bootstrap: int = Field(default=500, ge=50, le=5000)


EstimatorConfig = Annotated[
    DifferenceInMeansConfig
    | DifferenceInProportionsConfig
    | RegressionAdjustedConfig
    | CupedConfig
    | AIPWConfig
    | WeightingConfig
    | OutcomeRegressionConfig,
    Field(discriminator="kind"),
]


def build_estimator(config: EstimatorConfig, *, seed: int) -> Estimator:
    match config:
        case DifferenceInMeansConfig():
            return DifferenceInMeans(config.treatment)
        case DifferenceInProportionsConfig():
            return DifferenceInProportions(config.treatment)
        case RegressionAdjustedConfig():
            return RegressionAdjustedITT(config.treatment, config.covariates)
        case CupedConfig():
            return CupedITT(config.treatment, config.pre_metric)
        case AIPWConfig():
            return AIPWEstimator(config.treatment, config.covariates)
        case WeightingConfig():
            return WeightingEstimator(
                config.treatment,
                config.covariates,
                config.scheme,
                seed=seed,
                n_bootstrap=config.n_bootstrap,
            )
        case OutcomeRegressionConfig():
            return OutcomeRegressionEstimator(
                config.treatment, config.covariates, seed=seed, n_bootstrap=config.n_bootstrap
            )
    raise ValueError(f"unsupported estimator configuration: {config!r}")
