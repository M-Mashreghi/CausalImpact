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
