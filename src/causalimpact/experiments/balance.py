"""Baseline balance for randomized experiments (Task 2.3).

Descriptive only. Imbalance after randomization is chance, so it is reported as a
warning that motivates (pre-specified) covariate adjustment, never as evidence that
randomization failed and never via balance p-values. Assignment validity is judged by
the integrity and SRM checks instead.
"""

from __future__ import annotations

import pandas as pd

from causalimpact.diagnostics.balance import (
    DEFAULT_SMD_THRESHOLD,
    balance_table,
    summarize_balance,
)
from causalimpact.diagnostics.base import DiagnosticResult
from causalimpact.domain.variables import CovariateSpec, Eligibility, classify_covariate
from causalimpact.experiments.spec import ExperimentSpec

NAME = "baseline_balance"


def check_baseline_balance(
    spec: ExperimentSpec,
    data: pd.DataFrame,
    covariates: tuple[CovariateSpec, ...],
    *,
    threshold: float = DEFAULT_SMD_THRESHOLD,
) -> DiagnosticResult:
    not_baseline = [
        c.name for c in covariates if classify_covariate(c).eligibility is not Eligibility.ELIGIBLE
    ]
    if not_baseline:
        raise ValueError(
            "baseline balance requires covariates known to be pre-treatment and not affected "
            f"by treatment; not eligible: {not_baseline}"
        )
    missing = [c for c in [spec.arm_column, *(c.name for c in covariates)] if c not in data]
    if missing:
        raise ValueError(f"data is missing columns {missing}")
    rows = balance_table(data, spec.arm_column, spec.control_arm, covariates)
    result = summarize_balance(
        NAME,
        rows,
        threshold=threshold,
        imbalance_message=(
            f"baseline |SMD| > {threshold:g}; under valid randomization this is chance "
            "imbalance. Consider pre-specified covariate adjustment; do not re-randomize "
            "or drop units post hoc."
        ),
    )
    note = "descriptive balance only; no balance hypothesis tests are used as a validity gate"
    return result.model_copy(update={"notes": (*result.notes, note)})
