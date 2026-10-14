"""Task 1.3: DataFrame validation rejects malformed treatments and outcomes."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    DataContract,
    MissingnessPolicy,
    OutcomeKind,
    OutcomeSpec,
    TreatmentSpec,
    TriState,
)
from causalimpact.validation import SchemaValidationError, ensure_valid, validate_frame


def contract(kind: OutcomeKind = OutcomeKind.CONTINUOUS, **kw: Any) -> DataContract:
    return DataContract(
        treatment=TreatmentSpec(name="treated"),
        outcome=OutcomeSpec(name="y", kind=kind, measurement_time="d30"),
        covariates=(
            CovariateSpec(
                name="age",
                dtype=CovariateDType.NUMERIC,
                measurement_time="signup",
                pre_treatment=TriState.TRUE,
                descendant_of_treatment=TriState.FALSE,
                missingness_policy=kw.pop("age_missingness", MissingnessPolicy.FORBID),
            ),
        ),
        **kw,
    )


@pytest.fixture
def clean(rng: np.random.Generator) -> pd.DataFrame:
    n = 40
    return pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(n)],
            "treated": np.tile([0, 1], n // 2),
            "y": rng.normal(size=n),
            "age": rng.integers(18, 80, size=n).astype(float),
        }
    )


def test_clean_frame_passes(clean: pd.DataFrame) -> None:
    report = ensure_valid(clean, contract())
    assert report.is_valid
    assert report.issues == ()
    assert report.n_rows == 40


def test_binary_and_count_outcomes_pass(clean: pd.DataFrame) -> None:
    clean["y"] = np.tile([0, 1, 1, 0], 10)
    assert validate_frame(clean, contract(OutcomeKind.BINARY)).is_valid
    assert validate_frame(clean, contract(OutcomeKind.COUNT)).is_valid


def _codes(df: pd.DataFrame, c: DataContract | None = None) -> set[str]:
    report = validate_frame(df, c or contract())
    assert not report.is_valid
    return {i.code for i in report.errors}


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda d: d.drop(columns="y"), "missing_column"),
        (lambda d: d.drop(columns="age"), "missing_column"),
        (lambda d: d.assign(treated=d.treated.where(d.index != 3)), "missing_treatment"),
        (lambda d: d.assign(treated=d.treated.replace(1, 2)), "invalid_treatment_value"),
        (lambda d: d.assign(treated=0), "single_arm"),
        (lambda d: d.assign(y="high"), "non_numeric_outcome"),
        (lambda d: d.assign(y=d.y.where(d.index != 0, np.inf)), "non_finite_outcome"),
        (lambda d: d.assign(y=np.nan), "all_outcomes_missing"),
        (lambda d: d.assign(unit_id="same"), "duplicate_unit_id"),
        (lambda d: d.assign(unit_id=d.unit_id.where(d.index != 5)), "missing_unit_id"),
        (lambda d: d.assign(age=d.age.where(d.index != 2)), "missing_covariate"),
        (lambda d: d.assign(age="old"), "covariate_dtype"),
    ],
)
def test_malformed_frames_rejected(clean: pd.DataFrame, mutate: Any, code: str) -> None:
    assert code in _codes(mutate(clean))


def test_boolean_outcome_is_not_silently_numeric(clean: pd.DataFrame) -> None:
    clean["y"] = clean["y"] > 0
    assert "non_numeric_outcome" in _codes(clean, contract(OutcomeKind.BINARY))


def test_binary_outcome_must_be_zero_one(clean: pd.DataFrame) -> None:
    clean["y"] = np.tile([0, 2], 20)
    assert "invalid_binary_outcome" in _codes(clean, contract(OutcomeKind.BINARY))


@pytest.mark.parametrize("bad", [-1.0, 1.5])
def test_count_outcome_must_be_non_negative_integer(clean: pd.DataFrame, bad: float) -> None:
    clean["y"] = 3.0
    clean.loc[0, "y"] = bad
    assert "invalid_count_outcome" in _codes(clean, contract(OutcomeKind.COUNT))


def test_missing_outcomes_are_a_visible_warning(clean: pd.DataFrame) -> None:
    clean.loc[[1, 2], "y"] = np.nan
    report = validate_frame(clean, contract())
    assert report.is_valid
    assert [w.code for w in report.warnings] == ["missing_outcome"]
    assert "2 missing" in report.warnings[0].message


def test_declared_missingness_policy_allows_missing_covariate(clean: pd.DataFrame) -> None:
    clean.loc[0, "age"] = np.nan
    c = contract(age_missingness=MissingnessPolicy.INDICATOR)
    assert validate_frame(clean, c).is_valid


def test_string_treatment_levels(clean: pd.DataFrame) -> None:
    clean["treated"] = np.tile(["control", "variant"], 20)
    c = DataContract(
        treatment=TreatmentSpec(name="treated", control_value="control", treated_value="variant"),
        outcome=OutcomeSpec(name="y", kind=OutcomeKind.CONTINUOUS, measurement_time="d30"),
    )
    assert validate_frame(clean, c).is_valid


@pytest.mark.parametrize("bad", [-1.0, np.nan, np.inf])
def test_invalid_sample_weights(clean: pd.DataFrame, bad: float) -> None:
    clean["w"] = 1.0
    clean.loc[0, "w"] = bad
    assert "invalid_weight" in _codes(clean, contract(sample_weight="w"))


def test_missing_cluster_label(clean: pd.DataFrame) -> None:
    clean["cluster"] = ["c1"] * 39 + [None]
    assert "missing_design_label" in _codes(clean, contract(cluster_id="cluster"))


def test_timestamp_must_be_datetime(clean: pd.DataFrame) -> None:
    clean["ts"] = "2026-01-01"
    assert "invalid_timestamp" in _codes(clean, contract(timestamp="ts"))
    clean["ts"] = pd.Timestamp("2026-01-01", tz="UTC")
    assert validate_frame(clean, contract(timestamp="ts")).is_valid


def test_ensure_valid_raises_with_report(clean: pd.DataFrame) -> None:
    with pytest.raises(SchemaValidationError, match="treated") as excinfo:
        ensure_valid(clean.assign(treated=7), contract())
    assert not excinfo.value.report.is_valid
