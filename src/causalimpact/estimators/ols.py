"""Small, transparent OLS with heteroskedasticity-robust (HC2) covariance.

Kept dependency-free so that every number in an estimate can be traced to a formula:

    beta = (X'X)^-1 X'y
    V_HC2 = (X'X)^-1 X' diag(e_i^2 / (1 - h_ii)) X (X'X)^-1
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class OLSFit:
    coef: np.ndarray
    cov: np.ndarray
    residuals: np.ndarray
    n: int
    k: int

    @property
    def df_resid(self) -> int:
        return self.n - self.k


def ols_hc2(design: np.ndarray, y: np.ndarray) -> OLSFit:
    n, k = design.shape
    if n <= k:
        raise ValueError(f"need more observations ({n}) than parameters ({k})")
    if np.linalg.matrix_rank(design) < k:
        raise ValueError("design matrix is rank deficient (collinear or constant covariates)")
    xtx_inv = np.linalg.inv(design.T @ design)
    coef = xtx_inv @ design.T @ y
    resid = y - design @ coef
    leverage = np.einsum("ij,jk,ik->i", design, xtx_inv, design)
    if np.any(leverage >= 1.0 - 1e-12):
        raise ValueError("observation with leverage 1; HC2 covariance is undefined")
    meat = (design * (resid**2 / (1.0 - leverage))[:, None]).T @ design
    cov = xtx_inv @ meat @ xtx_inv
    return OLSFit(coef=coef, cov=cov, residuals=resid, n=n, k=k)


def ols_cluster_robust(design: np.ndarray, y: np.ndarray, clusters: np.ndarray) -> OLSFit:
    """OLS with CR1 cluster-robust covariance.

    V = c (X'X)^-1 [sum_g X_g' e_g e_g' X_g] (X'X)^-1,  c = G/(G-1) * (N-1)/(N-K)
    """
    n, k = design.shape
    if n <= k:
        raise ValueError(f"need more observations ({n}) than parameters ({k})")
    if np.linalg.matrix_rank(design) < k:
        raise ValueError("design matrix is rank deficient (collinear regressors)")
    labels, codes = np.unique(clusters, return_inverse=True)
    g = labels.size
    if g < 2:
        raise ValueError("cluster-robust inference needs at least two clusters")
    xtx_inv = np.linalg.inv(design.T @ design)
    coef = xtx_inv @ design.T @ y
    resid = y - design @ coef
    scores = np.zeros((g, k))
    np.add.at(scores, codes, design * resid[:, None])
    meat = scores.T @ scores
    factor = g / (g - 1) * (n - 1) / (n - k)
    cov = factor * xtx_inv @ meat @ xtx_inv
    return OLSFit(coef=coef, cov=cov, residuals=resid, n=n, k=k)


def two_way_demean(values: np.ndarray, unit: np.ndarray, period: np.ndarray) -> np.ndarray:
    """Remove unit and period means (exact two-way fixed effects for a balanced panel)."""
    frame = np.atleast_2d(values.T).T
    out = np.empty_like(frame, dtype=float)
    _, u = np.unique(unit, return_inverse=True)
    _, t = np.unique(period, return_inverse=True)
    for j in range(frame.shape[1]):
        col = frame[:, j].astype(float)
        unit_mean = np.bincount(u, col) / np.bincount(u)
        time_mean = np.bincount(t, col) / np.bincount(t)
        out[:, j] = col - unit_mean[u] - time_mean[t] + col.mean()
    return out if values.ndim > 1 else out[:, 0]
