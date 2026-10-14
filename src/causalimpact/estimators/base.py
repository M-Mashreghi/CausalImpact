"""Estimator contract shared across design families.

An estimator declares the estimand types it can target. ``run_estimator`` refuses an
estimand the estimator does not support (rather than quietly estimating something else)
and verifies that the returned output declares the requested estimand.
"""

from __future__ import annotations

from typing import Protocol

import pandas as pd

from causalimpact.domain.estimands import (
    EffectEstimate,
    Estimand,
    EstimandMismatchError,
    EstimandType,
    check_estimate_targets,
)


class Estimator(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def supported_estimands(self) -> frozenset[EstimandType]: ...

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate: ...


def run_estimator(
    estimator: Estimator,
    data: pd.DataFrame,
    estimand: Estimand,
    *,
    confidence_level: float = 0.95,
) -> EffectEstimate:
    if estimand.type not in estimator.supported_estimands:
        supported = sorted(t.value for t in estimator.supported_estimands)
        raise EstimandMismatchError(
            f"estimator {estimator.name!r} cannot target {estimand.type}; supports {supported}"
        )
    output = estimator.estimate(data, estimand, confidence_level=confidence_level)
    check_estimate_targets(estimand, output)
    if output.estimator != estimator.name:
        raise EstimandMismatchError(
            f"output reports estimator {output.estimator!r}, expected {estimator.name!r}"
        )
    if output.confidence_level != confidence_level:
        raise EstimandMismatchError("output confidence level differs from the requested one")
    return output
