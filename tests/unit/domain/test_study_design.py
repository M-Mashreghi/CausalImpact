"""Task 1.2: StudyDesign lifecycle and core-field validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from pydantic import ValidationError

from causalimpact.domain import (
    ALLOWED_DESIGN_TRANSITIONS,
    DesignFamily,
    DesignNotReadyError,
    DesignStatus,
    IllegalTransitionError,
    StudyDesign,
    TargetPopulation,
)


def always_ready(_: StudyDesign) -> list[str]:
    return []


def make_design(**overrides: Any) -> StudyDesign:
    fields: dict[str, Any] = {
        "title": "Checkout redesign",
        "research_question": "Does the new checkout increase conversion?",
        "design_family": DesignFamily.RANDOMIZED_EXPERIMENT,
        "target_population": TargetPopulation(
            name="eligible_users", description="Logged-in users reaching checkout"
        ),
        "unit_of_analysis": "user",
        "treatment": "new_checkout",
        "outcome": "converted",
        "estimand_id": "itt_conversion",
    }
    fields.update(overrides)
    return StudyDesign(**fields)


def advance_to(design: StudyDesign, target: DesignStatus) -> StudyDesign:
    path = [
        DesignStatus.VALIDATED,
        DesignStatus.ANALYSIS_READY,
        DesignStatus.ESTIMATED,
        DesignStatus.REVIEWED,
        DesignStatus.REPORTED,
    ]
    for status in path:
        if design.status is target:
            break
        design = design.transition(status, reason="advance", readiness_check=always_ready)
    return design


class TestCoreFields:
    def test_new_design_defaults(self) -> None:
        design = make_design()
        assert design.status is DesignStatus.DRAFT
        assert design.version == 1
        assert design.design_id.startswith("design_")
        assert design.created_at.tzinfo is not None

    @pytest.mark.parametrize(
        "missing",
        [
            "title",
            "research_question",
            "design_family",
            "target_population",
            "unit_of_analysis",
            "treatment",
            "outcome",
        ],
    )
    def test_missing_core_field_fails(self, missing: str) -> None:
        fields = make_design().model_dump(exclude={"design_id", "created_at"})
        del fields[missing]
        with pytest.raises(ValidationError, match=missing):
            StudyDesign(**fields)

    @pytest.mark.parametrize("field", ["title", "treatment", "outcome", "unit_of_analysis"])
    def test_blank_core_field_fails(self, field: str) -> None:
        with pytest.raises(ValidationError, match="must not be blank"):
            make_design(**{field: "   "})

    def test_unknown_design_family_fails(self) -> None:
        with pytest.raises(ValidationError):
            make_design(design_family="instrumental_variables")

    def test_unknown_field_fails(self) -> None:
        with pytest.raises(ValidationError, match="Extra inputs"):
            make_design(favourite_estimator="ols")

    def test_treatment_equal_to_outcome_fails(self) -> None:
        with pytest.raises(ValidationError, match="treatment and outcome"):
            make_design(outcome="new_checkout")

    def test_treatment_cannot_be_post_treatment(self) -> None:
        with pytest.raises(ValidationError, match="post-treatment"):
            make_design(forbidden_post_treatment_variables=("new_checkout",))

    def test_malformed_design_id_fails(self) -> None:
        with pytest.raises(ValidationError, match="design_"):
            make_design(design_id="run_" + "0" * 32)

    def test_naive_timestamp_fails(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            make_design(created_at=datetime(2026, 1, 1))

    def test_design_is_immutable(self) -> None:
        design = make_design()
        with pytest.raises(ValidationError, match="frozen"):
            design.treatment = "something_else"  # type: ignore[misc]


class TestLifecycle:
    def test_full_happy_path(self) -> None:
        design = advance_to(make_design(), DesignStatus.REPORTED)
        assert design.status is DesignStatus.REPORTED
        assert [c.to_status for c in design.status_history] == [
            DesignStatus.VALIDATED,
            DesignStatus.ANALYSIS_READY,
            DesignStatus.ESTIMATED,
            DesignStatus.REVIEWED,
            DesignStatus.REPORTED,
        ]

    def test_transition_does_not_mutate_original(self) -> None:
        draft = make_design()
        validated = draft.transition(DesignStatus.VALIDATED, reason="checked")
        assert draft.status is DesignStatus.DRAFT
        assert validated.status is DesignStatus.VALIDATED
        assert validated.design_id == draft.design_id

    @pytest.mark.parametrize(
        ("source", "target"),
        [
            (s, t)
            for s in DesignStatus
            for t in DesignStatus
            if t not in ALLOWED_DESIGN_TRANSITIONS[s]
        ],
    )
    def test_illegal_transitions_fail(self, source: DesignStatus, target: DesignStatus) -> None:
        design = advance_to(make_design(), source)
        with pytest.raises(IllegalTransitionError):
            design.transition(target, reason="x", readiness_check=always_ready)

    def test_analysis_ready_fails_closed_by_default(self) -> None:
        validated = make_design().transition(DesignStatus.VALIDATED, reason="checked")
        with pytest.raises(DesignNotReadyError, match="fails closed"):
            validated.transition(DesignStatus.ANALYSIS_READY, reason="go")

    def test_analysis_ready_reports_readiness_problems(self) -> None:
        validated = make_design().transition(DesignStatus.VALIDATED, reason="checked")
        with pytest.raises(DesignNotReadyError, match="missing dag_version"):
            validated.transition(
                DesignStatus.ANALYSIS_READY,
                reason="go",
                readiness_check=lambda _: ["missing dag_version"],
            )

    def test_cannot_skip_validation(self) -> None:
        with pytest.raises(IllegalTransitionError):
            make_design().transition(
                DesignStatus.ANALYSIS_READY, reason="skip", readiness_check=always_ready
            )


class TestRevision:
    def test_revise_bumps_version_and_keeps_id(self) -> None:
        draft = make_design()
        revised = draft.revise(reason="clarify outcome", outcome="converted_7d")
        assert revised.version == 2
        assert revised.design_id == draft.design_id
        assert revised.outcome == "converted_7d"
        assert draft.outcome == "converted"

    def test_revised_fields_are_revalidated(self) -> None:
        with pytest.raises(ValidationError, match="treatment and outcome"):
            make_design().revise(reason="oops", outcome="new_checkout")

    def test_analysis_ready_design_must_return_to_draft_before_editing(self) -> None:
        ready = advance_to(make_design(), DesignStatus.ANALYSIS_READY)
        with pytest.raises(IllegalTransitionError, match="only Draft"):
            ready.revise(reason="edit", outcome="other")
        draft = ready.transition(DesignStatus.DRAFT, reason="reopen")
        assert draft.revise(reason="edit", outcome="other").status is DesignStatus.DRAFT

    @pytest.mark.parametrize("field", ["design_id", "version", "status", "created_at"])
    def test_protected_fields_not_revisable(self, field: str) -> None:
        with pytest.raises(IllegalTransitionError, match="not revisable"):
            make_design().revise(reason="x", **{field: None})


def test_serialization_round_trip() -> None:
    design = advance_to(make_design(dag_version="dag_v1"), DesignStatus.ANALYSIS_READY)
    restored = StudyDesign.model_validate_json(design.model_dump_json())
    assert restored == design
