"""Propensity score estimation behind a nuisance-model interface (Task 3.2).

The baseline model is logistic regression fitted by Newton-Raphson (IRLS) on standardised
covariates, with an optional L2 penalty on the slopes. It is deterministic: identical data
and configuration give identical scores. Scores are never clipped here; extreme values are
surfaced by the overlap diagnostics (Task 3.3) instead of being hidden.

Non-convergence (typically complete separation, i.e. a positivity failure) raises an
error rather than returning scores of exactly 0 or 1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd
from pydantic import JsonValue

from causalimpact.domain.fingerprint import content_hash
from causalimpact.domain.variables import CovariateSpec, TreatmentSpec
from causalimpact.estimators.design_matrix import covariate_matrix


class ConvergenceError(RuntimeError):
    """The nuisance model did not converge; its predictions must not be used."""


class FittedPropensityModel(Protocol):
    def predict(self, x: pd.DataFrame) -> np.ndarray: ...


class PropensityModel(Protocol):
    @property
    def name(self) -> str: ...

    def config(self) -> dict[str, JsonValue]: ...

    def fit(self, x: pd.DataFrame, treated: np.ndarray) -> FittedPropensityModel: ...


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out: np.ndarray = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


@dataclass(frozen=True)
class FittedLogistic:
    columns: tuple[str, ...]
    means: np.ndarray
    scales: np.ndarray
    coef: np.ndarray  # [intercept, standardised slopes...]
    n_iter: int

    def _design(self, x: pd.DataFrame) -> np.ndarray:
        if tuple(x.columns) != self.columns:
            raise ValueError("prediction covariates differ from the fitted covariates")
        z = (x.to_numpy(dtype=float) - self.means) / self.scales
        return np.column_stack([np.ones(len(z)), z])

    def predict(self, x: pd.DataFrame) -> np.ndarray:
        return _sigmoid(self._design(x) @ self.coef)

    def coefficients(self) -> dict[str, float]:
        """Coefficients on the original covariate scale."""
        slopes = self.coef[1:] / self.scales
        intercept = float(self.coef[0] - np.sum(slopes * self.means))
        return {"intercept": intercept} | {
            c: float(b) for c, b in zip(self.columns, slopes, strict=True)
        }


@dataclass(frozen=True)
class LogisticPropensity:
    l2_penalty: float = 0.0
    max_iter: int = 100
    tol: float = 1e-10
    name: str = "logistic_regression_irls"

    def config(self) -> dict[str, JsonValue]:
        return {
            "model": self.name,
            "l2_penalty": self.l2_penalty,
            "max_iter": self.max_iter,
            "tol": self.tol,
            "standardize": True,
        }

    def fit(self, x: pd.DataFrame, treated: np.ndarray) -> FittedLogistic:
        if self.l2_penalty < 0:
            raise ValueError("l2_penalty must be non-negative")
        t = np.asarray(treated, dtype=float)
        if not np.isin(t, (0.0, 1.0)).all():
            raise ValueError("treatment indicator must be 0/1")
        if t.min() == t.max():
            raise ValueError("both treatment groups are required to fit a propensity model")
        values = x.to_numpy(dtype=float)
        means = values.mean(axis=0)
        scales = values.std(axis=0)
        if np.any(scales == 0):
            constant = [c for c, s in zip(x.columns, scales, strict=True) if s == 0]
            raise ValueError(f"constant covariates cannot enter the propensity model: {constant}")
        design = np.column_stack([np.ones(len(values)), (values - means) / scales])
        k = design.shape[1]
        penalty = np.full(k, self.l2_penalty)
        penalty[0] = 0.0  # never penalise the intercept

        beta = np.zeros(k)
        beta[0] = np.log(t.mean() / (1 - t.mean()))
        n_iter = 0
        for _ in range(self.max_iter):
            n_iter += 1
            p = _sigmoid(design @ beta)
            w = p * (1 - p)
            gradient = design.T @ (t - p) - penalty * beta
            hessian = (design * w[:, None]).T @ design + np.diag(penalty)
            step = np.linalg.solve(hessian, gradient)
            beta = beta + step
            if np.max(np.abs(step)) < self.tol:
                break
            if np.max(np.abs(beta)) > 50:
                raise ConvergenceError(
                    "propensity coefficients diverging: likely complete separation "
                    "(a positivity violation). Inspect overlap or declare an L2 penalty."
                )
        else:
            raise ConvergenceError(f"no convergence within {self.max_iter} iterations")
        return FittedLogistic(
            columns=tuple(map(str, x.columns)),
            means=means,
            scales=scales,
            coef=beta,
            n_iter=n_iter,
        )


@dataclass(frozen=True)
class PropensityScores:
    """Fitted propensity scores plus the provenance needed to reproduce them."""

    unit_ids: np.ndarray
    treated: np.ndarray
    scores: np.ndarray
    nuisance_config: dict[str, JsonValue] = field(default_factory=dict)

    @property
    def fingerprint(self) -> str:
        return content_hash(self.nuisance_config)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {"unit_id": self.unit_ids, "treated": self.treated, "propensity": self.scores}
        )


def estimate_propensity(
    data: pd.DataFrame,
    treatment: TreatmentSpec,
    covariates: tuple[CovariateSpec, ...],
    *,
    model: PropensityModel | None = None,
    unit_id: str = "unit_id",
) -> PropensityScores:
    fitter: PropensityModel = model if model is not None else LogisticPropensity()
    if treatment.name not in data or unit_id not in data:
        raise ValueError(f"data needs {treatment.name!r} and {unit_id!r} columns")
    arm = data[treatment.name]
    if arm.isna().any() or not arm.isin([treatment.control_value, treatment.treated_value]).all():
        raise ValueError("treatment must be non-missing and use the declared levels")
    t = (arm == treatment.treated_value).to_numpy(dtype=float)
    x = covariate_matrix(data, covariates)
    fitted = fitter.fit(x, t)
    scores = fitted.predict(x)
    config: dict[str, JsonValue] = {
        **fitter.config(),
        "treatment": treatment.name,
        "covariates": [c.name for c in covariates],
        "design_columns": list(map(str, x.columns)),
    }
    if isinstance(fitted, FittedLogistic):
        config["coefficients"] = dict(fitted.coefficients())
        config["n_iter"] = fitted.n_iter
    return PropensityScores(
        unit_ids=data[unit_id].to_numpy(),
        treated=t,
        scores=scores,
        nuisance_config=config,
    )
