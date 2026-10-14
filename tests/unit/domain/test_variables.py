"""Task 1.3: covariate temporal-safety fixtures and contract construction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    DataContract,
    Eligibility,
    OutcomeKind,
    OutcomeSpec,
    TreatmentSpec,
    TriState,
    classify_covariate,
)

T, F, U = TriState.TRUE, TriState.FALSE, TriState.UNKNOWN


def cov(
    name: str,
    pre: TriState,
    desc: TriState,
    when: str | None = "baseline",
) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=CovariateDType.NUMERIC,
        measurement_time=when,
        pre_treatment=pre,
        descendant_of_treatment=desc,
    )


# Every legal (pre_treatment, descendant_of_treatment) combination and its classification.
TEMPORAL_FIXTURES = [
    ("age", T, F, Eligibility.ELIGIBLE),
    ("baseline_spend_unk_desc", T, U, Eligibility.REVIEW_REQUIRED),
    ("post_clicks", F, T, Eligibility.FORBIDDEN),
    ("post_unrelated", F, F, Eligibility.FORBIDDEN),
    ("post_unknown", F, U, Eligibility.FORBIDDEN),
    ("mystery_timing", U, F, Eligibility.REVIEW_REQUIRED),
    ("mystery_mediator", U, T, Eligibility.FORBIDDEN),
    ("fully_unknown", U, U, Eligibility.REVIEW_REQUIRED),
]


@pytest.mark.parametrize(("name", "pre", "desc", "expected"), TEMPORAL_FIXTURES)
def test_temporal_safety_classification(
    name: str, pre: TriState, desc: TriState, expected: Eligibility
) -> None:
    decision = classify_covariate(cov(name, pre, desc))
    assert decision.eligibility is expected
    assert decision.reasons


def test_default_metadata_is_unknown_and_blocks_automatic_inclusion() -> None:
    spec = CovariateSpec(name="region", dtype=CovariateDType.CATEGORICAL)
    assert classify_covariate(spec).eligibility is Eligibility.REVIEW_REQUIRED


def test_pre_treatment_descendant_is_contradictory() -> None:
    with pytest.raises(ValidationError, match="cannot be a descendant"):
        cov("x", T, T)


def test_pre_treatment_requires_measurement_time() -> None:
    with pytest.raises(ValidationError, match="measurement_time"):
        cov("x", T, F, when=None)


def make_contract(*covariates: CovariateSpec) -> DataContract:
    return DataContract(
        treatment=TreatmentSpec(name="treated"),
        outcome=OutcomeSpec(name="revenue", kind=OutcomeKind.CONTINUOUS, measurement_time="d30"),
        covariates=covariates,
    )


def test_contract_automatic_candidates_only_include_eligible() -> None:
    contract = make_contract(*(cov(n, p, d) for n, p, d, _ in TEMPORAL_FIXTURES))
    assert contract.automatic_adjustment_candidates() == ("age",)
    screen = contract.screen_covariates()
    assert {d.covariate for d in screen[Eligibility.FORBIDDEN]} == {
        "post_clicks",
        "post_unrelated",
        "post_unknown",
        "mystery_mediator",
    }
    assert len(screen[Eligibility.REVIEW_REQUIRED]) == 3


def test_contract_rejects_reused_columns() -> None:
    with pytest.raises(ValidationError, match="more than one role"):
        make_contract(cov("revenue", T, F))
    with pytest.raises(ValidationError, match="more than one role"):
        make_contract(cov("age", T, F), cov("age", T, F))


def test_cluster_cannot_be_treatment() -> None:
    with pytest.raises(ValidationError, match="design column"):
        DataContract(
            treatment=TreatmentSpec(name="treated"),
            outcome=OutcomeSpec(name="y", kind=OutcomeKind.BINARY, measurement_time="d7"),
            cluster_id="treated",
        )


def test_treatment_levels_must_differ() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        TreatmentSpec(name="arm", control_value="a", treated_value="a")


def test_unknown_outcome_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        OutcomeSpec(name="y", kind="survival", measurement_time="d7")  # type: ignore[arg-type]


def test_contract_round_trip() -> None:
    contract = make_contract(cov("age", T, F))
    assert DataContract.model_validate_json(contract.model_dump_json()) == contract
