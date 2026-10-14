"""Streamlit study designer page (Task 6.3).

Run with:  streamlit run src/causalimpact/dashboard/designer_app.py

All logic lives in ``designer.py``; this file only lays out widgets and shows results.
"""

from __future__ import annotations

import streamlit as st
from pydantic import ValidationError

from causalimpact.dags import DagRegistry
from causalimpact.dashboard.designer import (
    DesignForm,
    build_artifacts,
    register_and_promote,
    required_assumptions,
)
from causalimpact.domain import DesignFamily, EstimandRegistry, EstimandType


def _registries() -> tuple[EstimandRegistry, DagRegistry]:
    if "estimands" not in st.session_state:
        st.session_state["estimands"] = EstimandRegistry()
        st.session_state["dags"] = DagRegistry()
    return st.session_state["estimands"], st.session_state["dags"]


def main() -> None:
    st.title("CausalImpact study designer")
    st.caption("Define the design before any estimator is chosen.")

    family = DesignFamily(
        st.selectbox("Design family", [f.value for f in DesignFamily], key="design_family")
    )
    with st.form("design"):
        st.subheader("Question and population")
        title = st.text_input("Title", key="title")
        question = st.text_area("Research question", key="research_question")
        pop_name = st.text_input("Target population name", key="population_name")
        pop_desc = st.text_input("Target population description", key="population_description")
        unit = st.text_input("Unit of analysis", key="unit_of_analysis")

        st.subheader("Treatment, outcome, estimand")
        treatment = st.text_input("Treatment variable", key="treatment")
        outcome = st.text_input("Outcome variable", key="outcome")
        estimand_type = st.selectbox(
            "Estimand",
            [t.value for t in EstimandType if t is not EstimandType.CATE],
            key="estimand",
        )

        st.subheader("Identification")
        assignment = st.text_input("Assignment / exposure mechanism", key="assignment")
        randomization_unit = st.text_input("Randomization unit (experiments)", key="rand_unit")
        time_zero = st.text_input("Time zero", key="time_zero")
        interference = st.text_input("Interference assessment", key="interference")
        missingness = st.text_input("Missingness / attrition plan", key="missingness")
        overlap = st.text_input("Overlap expectations (observational)", key="overlap")
        inference_unit = st.text_input("Inference unit", key="inference_unit")
        cluster = st.text_input("Cluster variable (optional)", key="cluster")
        sensitivity = st.text_input("Sensitivity plan", key="sensitivity")
        primary = st.text_input("Primary analysis", key="primary")

        st.subheader("Causal DAG")
        edges = st.text_area("Edges ('cause -> effect', comma separated)", key="edges")
        unobserved = st.text_input("Unobserved nodes (comma separated)", key="unobserved")
        adjustment = st.text_input("Proposed adjustment set (comma separated)", key="adjustment")
        forbidden = st.text_input("Forbidden post-treatment variables", key="forbidden")

        st.subheader("Assumptions (justify each)")
        justifications = {
            a.key: st.text_input(f"{a.key}: {a.statement}", key=f"assumption_{a.key}")
            for a in required_assumptions(family)
        }
        submitted = st.form_submit_button("Validate and promote to AnalysisReady")

    if not submitted:
        return
    estimands, dags = _registries()
    try:
        form = DesignForm(
            title=title,
            research_question=question,
            design_family=family,
            population_name=pop_name,
            population_description=pop_desc,
            unit_of_analysis=unit,
            treatment=treatment,
            outcome=outcome,
            estimand_type=EstimandType(estimand_type),
            assignment_mechanism=assignment,
            randomization_unit=randomization_unit,
            time_zero=time_zero,
            interference_assessment=interference,
            missingness_plan=missingness,
            overlap_expectations=overlap,
            inference_unit=inference_unit,
            cluster_variable=cluster,
            sensitivity_plan=sensitivity,
            primary_analysis=primary,
            dag_edges=edges,
            unobserved_nodes=unobserved,
            adjustment_variables=adjustment,
            forbidden_post_treatment=forbidden,
            assumption_justifications=justifications,
        )
        outcome_ = register_and_promote(build_artifacts(form), estimands, dags)
    except (ValidationError, ValueError) as exc:
        st.error(f"The design is malformed: {exc}")
        return
    if outcome_.ready:
        st.success(f"Design {outcome_.design.design_id} is AnalysisReady.")
        st.json(outcome_.design.model_dump(mode="json"))
    else:
        st.error("The design cannot become AnalysisReady:")
        for problem in outcome_.problems:
            st.write(f"- {problem}")


main()
