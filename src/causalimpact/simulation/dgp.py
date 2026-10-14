"""Synthetic data-generating processes with known effects (Task 7.1).

Each generator draws potential-outcome-based data from a typed configuration and a seed
and returns a ``SimulatedDataset`` carrying the data *and* the true estimands, so
benchmarks can compare estimates with the truth. Truths are the sample-level averages of
the known unit effects tau_i over the relevant units (all, treated, control, or overlap
weighted with the true propensity); where a population value is known in closed form it
is recorded too.

Failure-mode switches (sample ratio mismatch, differential attrition, clustering,
pre-trends, anticipation, staggered heterogeneous effects) exist so diagnostics can be
stress-tested (Task 7.6).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from causalimpact.domain.fingerprint import derive_seed
from causalimpact.ingestion.dataset_version import dataset_version


class _Config(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class RCTConfig(_Config):
    kind: Literal["rct"] = "rct"
    n: int = Field(default=2000, ge=20)
    treated_share: float = Field(default=0.5, gt=0.0, lt=1.0)
    realized_treated_share: float | None = Field(
        default=None,
        gt=0.0,
        lt=1.0,
        description="if set, assignment deviates from the design (SRM)",
    )
    effect: float = 0.5
    heterogeneity: float = 0.0
    noise_sd: float = Field(default=1.0, gt=0.0)
    prognostic_strength: float = 1.0
    binary_outcome: bool = False
    attrition_control: float = Field(default=0.0, ge=0.0, lt=1.0)
    attrition_treated: float = Field(default=0.0, ge=0.0, lt=1.0)
    cluster_size: int = Field(default=1, ge=1, description=">1 randomizes whole clusters")
    cluster_sd: float = Field(default=0.0, ge=0.0)


class ObservationalConfig(_Config):
    kind: Literal["observational"] = "observational"
    n: int = Field(default=2000, ge=20)
    confounding_strength: float = 1.0
    effect: float = 2.0
    heterogeneity: float = 1.0
    noise_sd: float = Field(default=1.0, gt=0.0)
    outcome_nonlinear: bool = False
    propensity_nonlinear: bool = False


class PanelConfig(_Config):
    kind: Literal["panel"] = "panel"
    n_units: int = Field(default=300, ge=4)
    n_periods: int = Field(default=8, ge=2)
    cohorts: tuple[int, ...] = (5,)
    never_treated_share: float = Field(default=0.4, ge=0.0, lt=1.0)
    dynamic_effects: tuple[float, ...] = (1.0, 2.0, 3.0)
    cohort_effect_scale: tuple[float, ...] | None = None
    pre_trend_slope: float = 0.0
    anticipation: float = 0.0
    noise_sd: float = Field(default=0.5, gt=0.0)
    n_clusters: int | None = Field(default=None, ge=2)
    cluster_shock_sd: float = Field(default=0.0, ge=0.0)


SimulationConfig = Annotated[
    RCTConfig | ObservationalConfig | PanelConfig, Field(discriminator="kind")
]


class SimulatedDataset(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    config: SimulationConfig
    seed: int
    data: pd.DataFrame
    truth: dict[str, float]

    @property
    def dataset_version(self) -> str:
        return dataset_version(self.data).content_hash

    def manifest(self) -> dict[str, object]:
        return {
            "config": self.config.model_dump(mode="json"),
            "seed": self.seed,
            "dataset_version": self.dataset_version,
            "truth": self.truth,
        }

    def save(self, directory: str | Path) -> Path:
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        self.data.to_csv(out / "data.csv", index=False, lineterminator="\n")
        (out / "truth.json").write_text(json.dumps(self.manifest(), indent=2), encoding="utf-8")
        return out


def _expit(z: np.ndarray) -> np.ndarray:
    out: np.ndarray = 1.0 / (1.0 + np.exp(-z))
    return out


def simulate(config: SimulationConfig, seed: int) -> SimulatedDataset:
    rng = np.random.default_rng(derive_seed(seed, f"simulation:{config.kind}"))
    if isinstance(config, RCTConfig):
        data, truth = _rct(config, rng)
    elif isinstance(config, ObservationalConfig):
        data, truth = _observational(config, rng)
    else:
        data, truth = _panel(config, rng)
    return SimulatedDataset(config=config, seed=seed, data=data, truth=truth)


def _rct(c: RCTConfig, rng: np.random.Generator) -> tuple[pd.DataFrame, dict[str, float]]:
    n_clusters = int(np.ceil(c.n / c.cluster_size))
    cluster = np.repeat(np.arange(n_clusters), c.cluster_size)[: c.n]
    share = c.realized_treated_share or c.treated_share
    treated_cluster = rng.random(n_clusters) < share
    t = treated_cluster[cluster]
    x = rng.normal(size=c.n)
    tau = c.effect + c.heterogeneity * x
    shock = rng.normal(0.0, c.cluster_sd, n_clusters)[cluster]
    base = c.prognostic_strength * x + shock
    if c.binary_outcome:
        p0 = _expit(-1.0 + base)
        p1 = np.clip(p0 + tau, 0.0, 1.0)
        y = rng.binomial(1, np.where(t, p1, p0)).astype(float)
        tau = p1 - p0
    else:
        y = 10.0 + base + tau * t + rng.normal(0.0, c.noise_sd, c.n)
    missing = rng.random(c.n) < np.where(t, c.attrition_treated, c.attrition_control)
    y = np.where(missing, np.nan, y)
    data = pd.DataFrame(
        {
            "unit_id": np.arange(c.n),
            "cluster_id": cluster,
            "arm": np.where(t, "treatment", "control"),
            "x_pre": x,
            "y": y,
        }
    )
    truth = {
        "ITT": float(tau.mean()),
        "ATE": float(tau.mean()),
        "population_ITT": float(c.effect) if not c.binary_outcome else float(tau.mean()),
    }
    return data, truth


def _observational(
    c: ObservationalConfig, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict[str, float]]:
    x = rng.normal(size=c.n)
    logit = c.confounding_strength * x
    if c.propensity_nonlinear:
        logit = -0.3 + c.confounding_strength * x - 0.8 * x**2
    e = _expit(logit)
    t = rng.binomial(1, e)
    tau = c.effect + c.heterogeneity * x
    mu0 = 1.0 + (np.exp(1.2 * x) if c.outcome_nonlinear else 3.0 * x)
    y = mu0 + tau * t + rng.normal(0.0, c.noise_sd, c.n)
    data = pd.DataFrame({"unit_id": np.arange(c.n), "treated": t, "x": x, "y": y})
    truth = {
        "ATE": float(tau.mean()),
        "ATT": float(np.sum(e * tau) / np.sum(e)),
        "ATC": float(np.sum((1 - e) * tau) / np.sum(1 - e)),
        "ATO": float(np.sum(e * (1 - e) * tau) / np.sum(e * (1 - e))),
        "population_ATE": float(c.effect),
    }
    return data, truth


def _panel(c: PanelConfig, rng: np.random.Generator) -> tuple[pd.DataFrame, dict[str, float]]:
    n_groups = len(c.cohorts)
    treated = rng.random(c.n_units) >= c.never_treated_share
    group = np.where(treated, rng.integers(0, n_groups, c.n_units), -1)
    start = np.where(group >= 0, np.asarray(c.cohorts)[np.maximum(group, 0)], np.nan)
    scale = (
        np.ones(n_groups) if c.cohort_effect_scale is None else np.asarray(c.cohort_effect_scale)
    )
    unit_fe = rng.normal(0.0, 2.0, c.n_units)
    time_fe = rng.normal(0.0, 1.0, c.n_periods + 1)
    cluster = np.arange(c.n_units) % c.n_clusters if c.n_clusters else np.arange(c.n_units)
    shocks = rng.normal(0.0, c.cluster_shock_sd, (cluster.max() + 1, c.n_periods + 1))
    rows, effects = [], []
    for i in range(c.n_units):
        for t in range(1, c.n_periods + 1):
            rel = t - start[i]
            eff = 0.0
            if group[i] >= 0 and rel >= 0:
                k = min(int(rel), len(c.dynamic_effects) - 1)
                eff = scale[group[i]] * c.dynamic_effects[k]
                effects.append(eff)
            elif group[i] >= 0 and rel == -1:
                eff = c.anticipation
            trend = c.pre_trend_slope * t * (group[i] >= 0)
            y = unit_fe[i] + time_fe[t] + shocks[cluster[i], t] + trend + eff
            rows.append(
                {
                    "unit_id": i,
                    "cluster_id": int(cluster[i]),
                    "period": t,
                    "treatment_start": start[i],
                    "outcome": y + rng.normal(0.0, c.noise_sd),
                }
            )
    truth = {"ATT_post_average": float(np.mean(effects)) if effects else 0.0}
    for k, value in enumerate(c.dynamic_effects):
        truth[f"dynamic_{k}"] = float(value * scale.mean()) if c.cohort_effect_scale else value
    return pd.DataFrame(rows), truth
