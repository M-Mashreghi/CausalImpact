"""Study-designer controller: form state -> validated design artifacts.

Pure functions used by the Streamlit page (``designer_app.py``) so the critical flow is
testable without a browser. No causal computation happens here: the controller builds
domain objects and delegates validation to ``DesignReadinessValidator``. A design that
fails validation stays out of AnalysisReady and the blocking problems are returned.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from causalimpact.dags import AdjustmentSet, CausalDAG, DagNode, DagRegistry
from causalimpact.design import DesignReadinessValidator, default_assumptions
from causalimpact.domain import (
    Assumption,
    DesignFamily,
    DesignNotReadyError,
    DesignStatus,
    Estimand,
    EstimandRegistry,
    EstimandType,
    StudyDesign,
    TargetPopulation,
    TreatmentBasis,
)


class DesignForm(BaseModel):
    """Everything the designer page collects, as plain strings and choices."""

    model_config = ConfigDict(extra="forbid")

    title: str = ""
    research_question: str = ""
    design_family: DesignFamily = DesignFamily.RANDOMIZED_EXPERIMENT
    population_name: str = ""
    population_description: str = ""
    unit_of_analysis: str = ""
    treatment: str = ""
    outcome: str = ""
    estimand_type: EstimandType = EstimandType.ITT
    assignment_mechanism: str = ""
    randomization_unit: str = ""
    time_zero: str = ""
    interference_assessment: str = ""
    missingness_plan: str = ""
    overlap_expectations: str = ""
    inference_unit: str = ""
    cluster_variable: str = ""
    sensitivity_plan: str = ""
    primary_analysis: str = ""
    dag_edges: str = Field(default="", description='e.g. "x -> treated, x -> y, treated -> y"')
    unobserved_nodes: str = ""
    adjustment_variables: str = ""
    forbidden_post_treatment: str = ""
    assumption_justifications: dict[str, str] = Field(default_factory=dict)


@dataclass(frozen=True)
class DesignArtifacts:
    design: StudyDesign
    estimand: Estimand
    dag: CausalDAG | None
    adjustment: AdjustmentSet | None


@dataclass(frozen=True)
class PromotionOutcome:
    ready: bool
    design: StudyDesign
    problems: tuple[str, ...]


def _opt(value: str) -> str | None:
    return value.strip() or None


def _names(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(n.strip() for n in text.split(",") if n.strip()))


def parse_edges(text: str) -> tuple[tuple[str, str], ...]:
    edges: list[tuple[str, str]] = []
    for chunk in text.split(","):
        if not chunk.strip():
            continue
        parts = [p.strip() for p in chunk.split("->")]
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"cannot parse edge {chunk.strip()!r}; use 'cause -> effect'")
        edges.append((parts[0], parts[1]))
    return tuple(edges)


def required_assumptions(family: DesignFamily) -> tuple[Assumption, ...]:
    return default_assumptions(family)


def build_artifacts(form: DesignForm) -> DesignArtifacts:
    """Build domain objects from the form; raises ValueError on malformed input."""
    population = TargetPopulation(
        name=form.population_name, description=form.population_description
    )
    estimand = Estimand(
        estimand_id=f"{form.estimand_type.value.lower()}_{form.outcome.strip()}",
        type=form.estimand_type,
        treatment=form.treatment,
        outcome=form.outcome,
        target_population=population,
        treatment_basis=TreatmentBasis.ASSIGNMENT
        if form.estimand_type is EstimandType.ITT
        else TreatmentBasis.RECEIPT,
    )
    dag: CausalDAG | None = None
    adjustment: AdjustmentSet | None = None
    edges = parse_edges(form.dag_edges)
    if edges:
        unobserved = set(_names(form.unobserved_nodes))
        nodes = sorted({n for e in edges for n in e})
        dag = CausalDAG(
            name=form.title or "study dag",
            nodes=tuple(DagNode(name=n, observed=n not in unobserved) for n in nodes),
            edges=edges,
        )
        adjustment = AdjustmentSet(
            dag_version=dag.version,
            treatment=form.treatment,
            outcome=form.outcome,
            variables=frozenset(_names(form.adjustment_variables)),
            rationale="declared in the study designer",
        )
    assumptions = tuple(
        a.justify(form.assumption_justifications[a.key])
        if form.assumption_justifications.get(a.key, "").strip()
        else a
        for a in default_assumptions(form.design_family)
    )
    design = StudyDesign(
        title=form.title,
        research_question=form.research_question,
        design_family=form.design_family,
        target_population=population,
        unit_of_analysis=form.unit_of_analysis,
        treatment=form.treatment,
        outcome=form.outcome,
        assignment_mechanism=_opt(form.assignment_mechanism),
        randomization_unit=_opt(form.randomization_unit),
        time_zero=_opt(form.time_zero),
        estimand_id=estimand.estimand_id,
        dag_version=None if dag is None else dag.version,
        adjustment_set_version=None if adjustment is None else adjustment.version,
        forbidden_post_treatment_variables=_names(form.forbidden_post_treatment),
        interference_assessment=_opt(form.interference_assessment),
        missingness_plan=_opt(form.missingness_plan),
        overlap_expectations=_opt(form.overlap_expectations),
        inference_unit=_opt(form.inference_unit),
        cluster_variable=_opt(form.cluster_variable),
        sensitivity_plan=_opt(form.sensitivity_plan),
        primary_analysis=_opt(form.primary_analysis),
        assumptions=assumptions,
    )
    return DesignArtifacts(design=design, estimand=estimand, dag=dag, adjustment=adjustment)


def register_and_promote(
    artifacts: DesignArtifacts, estimands: EstimandRegistry, dags: DagRegistry
) -> PromotionOutcome:
    """Register artifacts, then try Draft -> Validated -> AnalysisReady (fail closed)."""
    estimands.register(artifacts.estimand)
    if artifacts.dag is not None:
        dags.register_dag(artifacts.dag)
    if artifacts.adjustment is not None:
        dags.register_adjustment_set(artifacts.adjustment)
    validated = artifacts.design.transition(DesignStatus.VALIDATED, reason="study designer")
    try:
        ready = validated.transition(
            DesignStatus.ANALYSIS_READY,
            reason="study designer",
            readiness_check=DesignReadinessValidator(estimands, dags),
        )
    except DesignNotReadyError as exc:
        return PromotionOutcome(ready=False, design=validated, problems=tuple(str(exc).split("; ")))
    return PromotionOutcome(ready=True, design=ready, problems=())
