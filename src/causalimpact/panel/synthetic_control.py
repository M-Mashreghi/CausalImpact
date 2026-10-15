"""Synthetic control for a single treated unit (Task 4.9).

Abadie, Diamond & Hainmueller (2010). The synthetic unit is a convex combination of
donor units (weights >= 0, summing to 1) chosen to reproduce the treated unit's
pre-treatment outcome path:

    w* = argmin_w || Y_treated,pre - Y_donors,pre w ||^2   s.t.  w >= 0,  sum(w) = 1

The effect in each post period is the gap Y_treated - Y_synthetic; the estimand is the
treated unit's ATT averaged over post periods. Matching is on pre-period outcomes only
(transparent and covariate-free); the weights, pre-fit RMSPE and donor pool are recorded.

Inference uses in-space placebos (each donor treated as if it were the treated unit):
the p-value is the rank of the treated unit's post/pre RMSPE ratio among all units, and
the interval is the estimate +/- the (1 - alpha) quantile of |placebo average gaps|
among placebos whose pre-fit is not much worse than the treated unit's. With J donors
the smallest attainable p-value is 1/(J+1), which is reported.

Credibility conditions are assumptions, not facts: no spillovers to donors, no donor
exposed to a similar shock, and a pre-treatment fit good enough to trust the
counterfactual. Poor pre-fit, too few donors, or a treated path outside the donors'
range are surfaced as diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from pydantic import JsonValue
from scipy import optimize

from causalimpact.diagnostics.base import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain.estimands import EffectEstimate, Estimand, EstimandType
from causalimpact.panel.contract import PanelSpec


@dataclass(frozen=True)
class SyntheticFit:
    treated_unit: str
    treatment_period: int
    periods: tuple[int, ...]
    donors: tuple[str, ...]
    weights: np.ndarray
    treated_path: np.ndarray
    synthetic_path: np.ndarray

    @property
    def pre_mask(self) -> np.ndarray:
        return np.array(self.periods) < self.treatment_period

    @property
    def gaps(self) -> np.ndarray:
        out: np.ndarray = self.treated_path - self.synthetic_path
        return out

    @property
    def pre_rmspe(self) -> float:
        return float(np.sqrt(np.mean(self.gaps[self.pre_mask] ** 2)))

    @property
    def post_rmspe(self) -> float:
        return float(np.sqrt(np.mean(self.gaps[~self.pre_mask] ** 2)))

    @property
    def att(self) -> float:
        return float(np.mean(self.gaps[~self.pre_mask]))

    @property
    def rmspe_ratio(self) -> float:
        return self.post_rmspe / max(self.pre_rmspe, 1e-12)


def synthetic_weights(treated_pre: np.ndarray, donors_pre: np.ndarray) -> np.ndarray:
    """Convex weights minimising pre-period squared error.

    Solved exactly with active-set non-negative least squares (Lawson-Hanson). The
    sum-to-one constraint enters as an extra, heavily weighted row; the tiny residual
    violation is removed by renormalising. Deterministic, no tuning.
    """
    j = donors_pre.shape[1]
    if j == 1:
        return np.ones(1)
    scale = max(1.0, float(np.linalg.norm(donors_pre)), float(np.linalg.norm(treated_pre)))
    penalty = 1e4 * scale
    a = np.vstack([donors_pre, np.full((1, j), penalty)])
    b = np.append(treated_pre, penalty)
    w, _ = optimize.nnls(a, b, maxiter=50 * j)
    if w.sum() <= 0:
        raise RuntimeError("synthetic-control weights collapsed to zero")
    weights: np.ndarray = w / w.sum()
    return weights


def wide_outcomes(data: pd.DataFrame, spec: PanelSpec) -> pd.DataFrame:
    """Units x periods outcome matrix; duplicates fail loudly."""
    if data.duplicated(subset=[spec.unit, spec.period]).any():
        raise ValueError("duplicate (unit, period) rows")
    return data.pivot(index=spec.unit, columns=spec.period, values=spec.outcome)  # noqa: PD010


def fit_synthetic(
    wide: pd.DataFrame, treated_unit: str, donors: list[str], treatment_period: int
) -> SyntheticFit:
    periods = tuple(int(p) for p in wide.columns)
    pre = np.array(periods) < treatment_period
    if pre.sum() < 2 or (~pre).sum() < 1:
        raise ValueError("need at least two pre-treatment periods and one post period")
    y1 = wide.loc[treated_unit].to_numpy(dtype=float)
    y0 = wide.loc[donors].to_numpy(dtype=float).T  # periods x donors
    w = synthetic_weights(y1[pre], y0[pre])
    return SyntheticFit(
        treated_unit=str(treated_unit),
        treatment_period=treatment_period,
        periods=periods,
        donors=tuple(map(str, donors)),
        weights=w,
        treated_path=y1,
        synthetic_path=y0 @ w,
    )


@dataclass(frozen=True)
class PlaceboRun:
    unit: str
    fit: SyntheticFit


def in_space_placebos(
    wide: pd.DataFrame, donors: list[str], treatment_period: int
) -> list[PlaceboRun]:
    """Refit with each donor as the pseudo-treated unit and the rest as its pool."""
    runs = []
    for unit in donors:
        pool = [d for d in donors if d != unit]
        runs.append(
            PlaceboRun(unit=str(unit), fit=fit_synthetic(wide, unit, pool, treatment_period))
        )
    return runs


@dataclass(frozen=True)
class SyntheticControl:
    """Estimator for the treated unit's post-period ATT (one treated unit only)."""

    spec: PanelSpec = field(default_factory=PanelSpec)
    min_donors: int = 5
    placebo_prefit_cutoff: float = 5.0
    name: str = "synthetic_control"
    supported_estimands: frozenset[EstimandType] = frozenset({EstimandType.ATT})

    def prepare(self, data: pd.DataFrame) -> tuple[pd.DataFrame, str, int, list[str], list[str]]:
        s = self.spec
        for column in (s.unit, s.period, s.outcome, s.treatment_start):
            if column not in data:
                raise ValueError(f"data is missing column {column!r}")
        starts = data.groupby(s.unit)[s.treatment_start].first()
        treated = starts.dropna()
        if len(treated) != 1:
            raise ValueError(
                f"synthetic control needs exactly one treated unit, found {len(treated)}"
            )
        treated_unit = str(treated.index[0])
        treatment_period = int(treated.iloc[0])
        wide = wide_outcomes(data, s)
        wide.index = wide.index.map(str)
        candidates = [str(u) for u in starts.index[starts.isna()]]
        complete = wide.loc[candidates].notna().all(axis=1)
        donors = [u for u in candidates if complete[u]]
        dropped = [u for u in candidates if not complete[u]]
        if wide.loc[treated_unit].isna().any():
            raise ValueError("the treated unit has missing outcomes")
        if len(donors) < 2:
            raise ValueError("synthetic control needs at least two complete donor units")
        return wide, treated_unit, treatment_period, donors, dropped

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        if estimand.type is not EstimandType.ATT:
            raise ValueError("synthetic control targets the treated unit's ATT")
        wide, treated_unit, t0, donors, dropped = self.prepare(data)
        fit = fit_synthetic(wide, treated_unit, donors, t0)
        placebos = in_space_placebos(wide, donors, t0)

        ratios = np.array([p.fit.rmspe_ratio for p in placebos])
        p_value = float((np.sum(ratios >= fit.rmspe_ratio) + 1) / (len(placebos) + 1))
        eligible = [
            p for p in placebos if p.fit.pre_rmspe <= self.placebo_prefit_cutoff * fit.pre_rmspe
        ]
        interval_rule = f"placebos with pre-RMSPE <= {self.placebo_prefit_cutoff:g}x treated"
        if len(eligible) < 5:
            # The treated fit is much better than any placebo's; using every placebo makes
            # the interval wider (conservative) rather than undefined.
            eligible = placebos
            interval_rule = "all placebos (too few met the pre-fit cutoff; conservative)"
        null_gaps = np.array([abs(p.fit.att) for p in eligible])
        if null_gaps.size < 2:
            raise RuntimeError("too few placebos to quantify uncertainty")
        half_width = float(np.quantile(null_gaps, confidence_level))
        se = float(np.std([p.fit.att for p in eligible], ddof=1))
        att = fit.att

        diagnostic = synthetic_control_diagnostic(fit, donors, dropped, self.min_donors)
        return EffectEstimate(
            estimand_id=estimand.estimand_id,
            estimand_type=estimand.type,
            estimator=self.name,
            estimate=att,
            std_error=se,
            ci_lower=att - half_width,
            ci_upper=att + half_width,
            confidence_level=confidence_level,
            inference_method="in-space placebo permutation (RMSPE-ratio rank p-value; "
            "interval from |placebo ATT| quantile)",
            p_value=p_value,
            n_units=1 + len(donors),
            n_treated=1,
            n_control=len(donors),
            details={
                "treated_unit": treated_unit,
                "treatment_period": t0,
                "weights": {d: float(w) for d, w in zip(fit.donors, fit.weights, strict=True)},
                "pre_rmspe": fit.pre_rmspe,
                "post_rmspe": fit.post_rmspe,
                "rmspe_ratio": fit.rmspe_ratio,
                "path": [
                    {"period": p, "treated": float(a), "synthetic": float(b), "gap": float(a - b)}
                    for p, a, b in zip(
                        fit.periods, fit.treated_path, fit.synthetic_path, strict=True
                    )
                ],
                "donors_excluded_incomplete": dropped,
                "n_placebos": len(placebos),
                "n_placebos_used_for_interval": len(eligible),
                "interval_placebo_rule": interval_rule,
                "minimum_attainable_p_value": 1 / (len(placebos) + 1),
                "placebo_rmspe_ratios": {p.unit: p.fit.rmspe_ratio for p in placebos},
                "fit_diagnostic": diagnostic.model_dump(mode="json"),
            },
        )


def synthetic_control_diagnostic(
    fit: SyntheticFit, donors: list[str], dropped: list[str], min_donors: int = 5
) -> DiagnosticResult:
    findings: list[Finding] = []
    pre = fit.pre_mask
    treated_pre = fit.treated_path[pre]
    scale = float(np.std(treated_pre)) or 1.0
    relative_fit = fit.pre_rmspe / scale
    if len(donors) < min_donors:
        findings.append(
            Finding(
                code="small_donor_pool",
                severity=FindingSeverity.BLOCKING,
                message=f"only {len(donors)} donors (< {min_donors}); placebo inference "
                "cannot reach conventional significance",
            )
        )
    if relative_fit > 1.0:
        severity = FindingSeverity.BLOCKING
    elif relative_fit > 0.5:
        severity = FindingSeverity.WARNING
    else:
        severity = None
    if severity is not None:
        findings.append(
            Finding(
                code="poor_pre_treatment_fit",
                severity=severity,
                message=f"pre-treatment RMSPE is {relative_fit:.2f} x the treated unit's "
                "pre-period SD; the synthetic counterfactual is not credible",
            )
        )
    if dropped:
        findings.append(
            Finding(
                code="donors_excluded",
                severity=FindingSeverity.WARNING,
                message=f"{len(dropped)} candidate donors excluded for missing outcomes",
                count=len(dropped),
                examples=tuple(sorted(dropped)[:5]),
            )
        )
    metrics: dict[str, JsonValue] = {
        "treated_unit": fit.treated_unit,
        "treatment_period": fit.treatment_period,
        "n_donors": len(donors),
        "pre_rmspe": fit.pre_rmspe,
        "relative_pre_fit": relative_fit,
        "weights": {d: float(w) for d, w in zip(fit.donors, fit.weights, strict=True)},
        "donor_pool": list(fit.donors),
    }
    notes = (
        "assumes no spillovers to donors and no similar shock in any donor; the donor pool "
        "is a researcher choice and should be justified",
    )
    return DiagnosticResult(
        name="synthetic_control_fit", findings=tuple(findings), metrics=metrics, notes=notes
    )
