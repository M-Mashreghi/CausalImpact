"""Task 6.3: study-designer flow; invalid designs cannot reach AnalysisReady."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from causalimpact.dags import DagRegistry
from causalimpact.dashboard.designer import (
    DesignForm,
    PromotionOutcome,
    build_artifacts,
    parse_edges,
    register_and_promote,
    required_assumptions,
)
from causalimpact.domain import DesignFamily, DesignStatus, EstimandRegistry, EstimandType

pytestmark = pytest.mark.integration

APP = Path(__file__).resolve().parents[2] / "src/causalimpact/dashboard/designer_app.py"
OBS_JUSTIFIED = {a.key: "documented" for a in required_assumptions(DesignFamily.OBSERVATIONAL)}


def observational_form(**overrides: Any) -> DesignForm:
    fields: dict[str, Any] = {
        "title": "Programme effect",
        "research_question": "Does enrolment change y?",
        "design_family": DesignFamily.OBSERVATIONAL,
        "population_name": "members",
        "population_description": "Active members",
        "unit_of_analysis": "member",
        "treatment": "treated",
        "outcome": "y",
        "estimand_type": EstimandType.ATE,
        "assignment_mechanism": "self-selection",
        "time_zero": "enrolment",
        "interference_assessment": "none",
        "missingness_plan": "complete",
        "overlap_expectations": "broad",
        "inference_unit": "member",
        "sensitivity_plan": "trimming sweep",
        "primary_analysis": "AIPW",
        "dag_edges": "x -> treated, x -> y, treated -> m, m -> y, treated -> y",
        "adjustment_variables": "x",
        "forbidden_post_treatment": "m",
        "assumption_justifications": OBS_JUSTIFIED,
    }
    fields.update(overrides)
    return DesignForm(**fields)


def promote(form: DesignForm) -> PromotionOutcome:
    return register_and_promote(build_artifacts(form), EstimandRegistry(), DagRegistry())


def test_complete_form_reaches_analysis_ready() -> None:
    outcome = promote(observational_form())
    assert outcome.ready, outcome.problems
    assert outcome.design.status is DesignStatus.ANALYSIS_READY
    assert outcome.design.estimand_id == "ate_y"


@pytest.mark.parametrize(
    ("overrides", "problem"),
    [
        ({"adjustment_variables": "x, m"}, "'m' is unsafe: mediator"),
        ({"adjustment_variables": ""}, "backdoor criterion"),
        ({"time_zero": ""}, "missing required field: time_zero"),
        ({"assumption_justifications": {}}, "lacks a justification"),
        ({"dag_edges": ""}, "missing required field: dag_version"),
    ],
)
def test_invalid_designs_stay_out_of_analysis_ready(
    overrides: dict[str, Any], problem: str
) -> None:
    outcome = promote(observational_form(**overrides))
    assert not outcome.ready
    assert outcome.design.status is DesignStatus.VALIDATED
    assert any(problem in p for p in outcome.problems), outcome.problems


def test_edge_parsing() -> None:
    assert parse_edges(" a -> b ,b->c ") == (("a", "b"), ("b", "c"))
    with pytest.raises(ValueError, match="cannot parse"):
        parse_edges("a - b")


def test_streamlit_page_smoke_blocks_incomplete_design() -> None:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    at.text_input(key="title").input("Checkout redesign")
    at.text_input(key="treatment").input("arm")
    at.text_input(key="outcome").input("revenue")
    at.button[0].click().run()
    assert not at.exception
    assert any("cannot become AnalysisReady" in e.value or "malformed" in e.value for e in at.error)
    assert not at.success


def test_streamlit_page_smoke_promotes_complete_experiment() -> None:
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    values = {
        "title": "Checkout redesign",
        "population_name": "users",
        "population_description": "Logged-in users",
        "unit_of_analysis": "user",
        "treatment": "arm",
        "outcome": "revenue",
        "assignment": "50/50 hash",
        "rand_unit": "user",
        "time_zero": "first view",
        "interference": "none",
        "missingness": "complete",
        "inference_unit": "user",
        "sensitivity": "CUPED",
        "primary": "difference in means",
    }
    for key, value in values.items():
        at.text_input(key=key).input(value)
    at.text_area(key="research_question").input("Does the redesign increase revenue?")
    for a in required_assumptions(DesignFamily.RANDOMIZED_EXPERIMENT):
        at.text_input(key=f"assumption_{a.key}").input("documented")
    at.button[0].click().run()
    assert not at.exception
    assert at.success and "AnalysisReady" in at.success[0].value
