"""Validate a unit-level DataFrame against a DataContract.

Errors make the dataset unusable for estimation. Warnings are surfaced, never dropped:
missing outcomes, for example, are a warning here because attrition is diagnosed by a
dedicated diagnostic (Task 2.10) rather than silently discarded.
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict

from causalimpact.domain.variables import (
    CovariateDType,
    DataContract,
    MissingnessPolicy,
    OutcomeKind,
)


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


_Add = Callable[[str, str, "Severity", str], None]


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    column: str
    code: str
    severity: Severity
    message: str


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    n_rows: int
    issues: tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    def codes(self) -> set[str]:
        return {i.code for i in self.issues}


class SchemaValidationError(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        lines = [f"{i.column}: {i.message}" for i in report.errors]
        super().__init__("dataset violates its data contract:\n" + "\n".join(lines))


def _is_numeric(series: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)


def validate_frame(df: pd.DataFrame, contract: DataContract) -> ValidationReport:
    issues: list[ValidationIssue] = []

    def add(column: str, code: str, severity: Severity, message: str) -> None:
        issues.append(ValidationIssue(column=column, code=code, severity=severity, message=message))

    required = [contract.unit_id, contract.treatment.name, contract.outcome.name]
    required += [c.name for c in contract.covariates]
    optional_roles = (
        contract.timestamp,
        contract.cluster_id,
        contract.stratum,
        contract.sample_weight,
    )
    required += [c for c in optional_roles if c is not None]
    for column in dict.fromkeys(required):
        if column not in df.columns:
            add(column, "missing_column", Severity.ERROR, "required column is absent")
    if any(i.code == "missing_column" for i in issues):
        return ValidationReport(n_rows=len(df), issues=tuple(issues))

    _check_unit_id(df[contract.unit_id], add)
    _check_treatment(df[contract.treatment.name], contract, add)
    _check_outcome(df[contract.outcome.name], contract, add)
    for cov in contract.covariates:
        _check_covariate(df[cov.name], cov.dtype, cov.missingness_policy, add)
    if contract.sample_weight is not None:
        w = df[contract.sample_weight]
        if not _is_numeric(w) or w.isna().any() or not np.isfinite(w).all() or (w < 0).any():
            add(
                contract.sample_weight,
                "invalid_weight",
                Severity.ERROR,
                "weights must be finite, non-negative and non-missing",
            )
    for role in (contract.cluster_id, contract.stratum):
        if role is not None and df[role].isna().any():
            add(role, "missing_design_label", Severity.ERROR, "design labels must not be missing")
    if contract.timestamp is not None:
        ts = df[contract.timestamp]
        if not pd.api.types.is_datetime64_any_dtype(ts) or ts.isna().any():
            add(
                contract.timestamp,
                "invalid_timestamp",
                Severity.ERROR,
                "timestamps must be non-missing datetimes",
            )

    return ValidationReport(n_rows=len(df), issues=tuple(issues))


def ensure_valid(df: pd.DataFrame, contract: DataContract) -> ValidationReport:
    report = validate_frame(df, contract)
    if not report.is_valid:
        raise SchemaValidationError(report)
    return report


def _check_unit_id(units: pd.Series, add: _Add) -> None:
    if units.isna().any():
        add(str(units.name), "missing_unit_id", Severity.ERROR, "unit ids must not be missing")
    n_dup = int(units.duplicated().sum())
    if n_dup:
        add(
            str(units.name),
            "duplicate_unit_id",
            Severity.ERROR,
            f"{n_dup} duplicated unit ids in a unit-level dataset",
        )


def _check_treatment(series: pd.Series, contract: DataContract, add: _Add) -> None:
    col = contract.treatment.name
    if series.isna().any():
        add(col, "missing_treatment", Severity.ERROR, "treatment must not be missing")
    allowed = {contract.treatment.control_value, contract.treatment.treated_value}
    observed = set(series.dropna().unique().tolist())
    if unexpected := observed - allowed:
        add(
            col,
            "invalid_treatment_value",
            Severity.ERROR,
            f"unexpected treatment values {sorted(map(str, unexpected))}; allowed {allowed}",
        )
    elif len(observed) < 2:
        add(col, "single_arm", Severity.ERROR, "both treatment arms must be present")


def _check_outcome(series: pd.Series, contract: DataContract, add: _Add) -> None:
    col = contract.outcome.name
    kind = contract.outcome.kind
    n_missing = int(series.isna().sum())
    if n_missing == len(series):
        add(col, "all_outcomes_missing", Severity.ERROR, "outcome is entirely missing")
        return
    if n_missing:
        add(
            col,
            "missing_outcome",
            Severity.WARNING,
            f"{n_missing} missing outcomes; run attrition diagnostics before estimation",
        )
    if not _is_numeric(series):
        add(col, "non_numeric_outcome", Severity.ERROR, f"{kind} outcome must be numeric")
        return
    values = series.dropna().to_numpy(dtype=float)
    if not np.isfinite(values).all():
        add(col, "non_finite_outcome", Severity.ERROR, "outcome contains infinite values")
        return
    if kind is OutcomeKind.BINARY and not np.isin(values, (0.0, 1.0)).all():
        add(col, "invalid_binary_outcome", Severity.ERROR, "binary outcome must be 0/1")
    if kind is OutcomeKind.COUNT and ((values < 0).any() or (values % 1 != 0).any()):
        add(col, "invalid_count_outcome", Severity.ERROR, "count outcome must be integers >= 0")


def _check_covariate(
    series: pd.Series, dtype: CovariateDType, policy: MissingnessPolicy, add: _Add
) -> None:
    col = str(series.name)
    if series.isna().any() and policy is MissingnessPolicy.FORBID:
        add(
            col,
            "missing_covariate",
            Severity.ERROR,
            "covariate has missing values but its missingness policy is 'forbid'",
        )
    present = series.dropna()
    if dtype is CovariateDType.NUMERIC:
        if not _is_numeric(series):
            add(col, "covariate_dtype", Severity.ERROR, "numeric covariate is not numeric")
        elif not np.isfinite(present.to_numpy(dtype=float)).all():
            add(col, "covariate_non_finite", Severity.ERROR, "covariate has infinite values")
    elif dtype is CovariateDType.BINARY and not set(present.unique().tolist()) <= {0, 1}:
        add(col, "covariate_dtype", Severity.ERROR, "binary covariate must be 0/1")
