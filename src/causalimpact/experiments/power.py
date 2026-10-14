"""Power, minimum detectable effect and sample size planning (Task 2.7).

Planning only: these functions take *assumed* inputs (baseline rate or standard deviation,
allocation, alpha, target power) and never an observed estimate. Post-hoc "observed power"
is not offered because it is a function of the p-value and adds no information.

Two-sided tests with the normal approximation, matching the inference of the
difference-in-means / difference-in-proportions estimators:

    SE(n_t, n_c) = sqrt(v_t / n_t + v_c / n_c)
    power(delta) = Phi(|delta| / SE - z_{1-alpha/2}) + Phi(-|delta| / SE - z_{1-alpha/2})

with v = sigma^2 (continuous) or p(1 - p) (binary, unpooled), optionally multiplied by
(1 - variance_reduction) for a pre-declared CUPED / regression-adjustment gain.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy import optimize, stats


class MetricType(StrEnum):
    CONTINUOUS = "continuous"
    BINARY = "binary"


class PowerInputs(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    metric_type: MetricType
    alpha: float = Field(default=0.05, gt=0.0, lt=1.0)
    power: float = Field(default=0.8, gt=0.0, lt=1.0)
    treated_fraction: float = Field(default=0.5, gt=0.0, lt=1.0)
    std_dev: float | None = Field(default=None, gt=0.0)
    baseline_rate: float | None = Field(default=None, gt=0.0, lt=1.0)
    variance_reduction: float = Field(default=0.0, ge=0.0, lt=1.0)

    @model_validator(mode="after")
    def _metric_parameters(self) -> Self:
        if self.metric_type is MetricType.CONTINUOUS:
            if self.std_dev is None or self.baseline_rate is not None:
                raise ValueError("continuous metrics need std_dev (and no baseline_rate)")
        elif self.baseline_rate is None or self.std_dev is not None:
            raise ValueError("binary metrics need baseline_rate (and no std_dev)")
        return self

    @property
    def z_alpha(self) -> float:
        return float(stats.norm.ppf(1 - self.alpha / 2))

    @property
    def z_power(self) -> float:
        return float(stats.norm.ppf(self.power))

    def unit_variances(self, effect: float) -> tuple[float, float]:
        """(treated, control) per-unit outcome variances under the alternative ``effect``."""
        factor = 1.0 - self.variance_reduction
        if self.metric_type is MetricType.CONTINUOUS:
            assert self.std_dev is not None
            v = self.std_dev**2 * factor
            return v, v
        assert self.baseline_rate is not None
        p0 = self.baseline_rate
        p1 = p0 + effect
        if not 0.0 < p1 < 1.0:
            raise ValueError(f"baseline_rate + effect = {p1} is not a valid proportion")
        return p1 * (1 - p1) * factor, p0 * (1 - p0) * factor


class SampleSize(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n_treated: int
    n_control: int
    effect: float
    inputs: PowerInputs

    @property
    def n_total(self) -> int:
        return self.n_treated + self.n_control


def _split(inputs: PowerInputs, n_total: float) -> tuple[float, float]:
    a = inputs.treated_fraction
    return n_total * a, n_total * (1 - a)


def standard_error(inputs: PowerInputs, effect: float, n_total: float) -> float:
    n_t, n_c = _split(inputs, n_total)
    if min(n_t, n_c) <= 0:
        raise ValueError("sample size must be positive in both arms")
    v_t, v_c = inputs.unit_variances(effect)
    return math.sqrt(v_t / n_t + v_c / n_c)


def power(inputs: PowerInputs, effect: float, n_total: float) -> float:
    """Probability that a two-sided level-alpha test rejects when the true effect is ``effect``."""
    se = standard_error(inputs, effect, n_total)
    shift = abs(effect) / se
    z = inputs.z_alpha
    return float(stats.norm.cdf(shift - z) + stats.norm.cdf(-shift - z))


def sample_size(inputs: PowerInputs, effect: float) -> SampleSize:
    """Smallest per-arm sizes reaching ``inputs.power`` for ``effect`` (two-sided)."""
    if effect == 0.0:
        raise ValueError("cannot plan for a zero effect")
    v_t, v_c = inputs.unit_variances(effect)
    a = inputs.treated_fraction
    k = (inputs.z_alpha + inputs.z_power) ** 2 / effect**2
    n_total = k * (v_t / a + v_c / (1 - a))
    n_t, n_c = _split(inputs, n_total)
    return SampleSize(
        n_treated=math.ceil(n_t - 1e-9),
        n_control=math.ceil(n_c - 1e-9),
        effect=effect,
        inputs=inputs,
    )


def minimum_detectable_effect(inputs: PowerInputs, n_total: float) -> float:
    """Smallest positive effect detectable with ``inputs.power`` at total size ``n_total``.

    Uses the approximation that ignores the (negligible) opposite-tail rejection, so that
    ``sample_size(mde(n)) == n`` up to rounding.
    """
    target = inputs.z_alpha + inputs.z_power
    if inputs.metric_type is MetricType.CONTINUOUS:
        return target * standard_error(inputs, 0.0, n_total)
    assert inputs.baseline_rate is not None
    upper = 1.0 - inputs.baseline_rate - 1e-12

    def gap(delta: float) -> float:
        return delta - target * standard_error(inputs, delta, n_total)

    if gap(upper) < 0:
        raise ValueError("no detectable increase exists at this sample size")
    return float(optimize.brentq(gap, 1e-12, upper, xtol=1e-12))
