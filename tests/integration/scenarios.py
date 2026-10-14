"""End-to-end scenario fixtures shared by integration and API tests."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from causalimpact.dags import AdjustmentSet, CausalDAG, DagNode, DagRegistry
from causalimpact.design import default_assumptions
from causalimpact.diagnostics import DiagnosticResult
from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    DesignFamily,
    DesignStatus,
    Estimand,
    EstimandRegistry,
    EstimandType,
    StudyDesign,
    TargetPopulation,
    TreatmentBasis,
    TreatmentSpec,
    TriState,
)
from causalimpact.estimators import Estimator
from causalimpact.experiments import (
    Arm,
    ExperimentSpec,
    check_attrition,
    check_srm_from_assignments,
)
from causalimpact.experiments.estimators import DifferenceInMeans
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.observational.overlap import check_overlap
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.services import AnalysisService, DiagnosticStep

POP = TargetPopulation(name="users", description="Users in scope of the study")


def _justified(family: DesignFamily) -> tuple:  # type: ignore[type-arg]
    return tuple(
        a.justify(f"documented rationale for {a.key}") for a in default_assumptions(family)
    )


@dataclass
class Scenario:
    service: AnalysisService
    design: StudyDesign
    data: pd.DataFrame
    estimator: Estimator
    diagnostics: list[DiagnosticStep] = field(default_factory=list)


def _registries() -> tuple[EstimandRegistry, DagRegistry]:
    return EstimandRegistry(), DagRegistry()


def _ready(design: StudyDesign, service: AnalysisService) -> StudyDesign:
    from causalimpact.design import DesignReadinessValidator

    validated = design.transition(DesignStatus.VALIDATED, reason="reviewed")
    return validated.transition(
        DesignStatus.ANALYSIS_READY,
        reason="ready",
        readiness_check=DesignReadinessValidator(service.estimands, service.dags),
    )


def rct(
    rng: np.random.Generator, *, n: int = 4000, effect: float = 0.3, srm: bool = False
) -> Scenario:
    estimands, dags = _registries()
    estimands.register(
        Estimand(
            estimand_id="itt_revenue",
            type=EstimandType.ITT,
            treatment="arm",
            outcome="revenue",
            target_population=POP,
            treatment_basis=TreatmentBasis.ASSIGNMENT,
        )
    )
    service = AnalysisService(estimands, dags)
    design = StudyDesign(
        title="Checkout redesign",
        research_question="Does the redesign increase revenue per user?",
        design_family=DesignFamily.RANDOMIZED_EXPERIMENT,
        target_population=POP,
        unit_of_analysis="user_id",
        treatment="arm",
        outcome="revenue",
        assignment_mechanism="user-level 50/50 hash bucketing",
        randomization_unit="user_id",
        time_zero="first checkout view",
        estimand_id="itt_revenue",
        interference_assessment="no shared accounts",
        missingness_plan="revenue complete from billing",
        inference_unit="user_id",
        sensitivity_plan="CUPED and regression adjustment as robustness",
        primary_analysis="difference in means",
        assumptions=_justified(DesignFamily.RANDOMIZED_EXPERIMENT),
    )
    share = 0.45 if srm else 0.5
    arm = np.where(rng.random(n) < share, "treatment", "control")
    revenue = rng.normal(10, 3, n) + effect * (arm == "treatment")
    data = pd.DataFrame({"user_id": np.arange(n), "arm": arm, "revenue": revenue})
    spec = ExperimentSpec(
        experiment_id="checkout",
        arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
        control_arm="control",
        randomization_unit="user_id",
        analysis_unit="user_id",
        primary_metric="revenue",
    )

    def srm_check(df: pd.DataFrame) -> DiagnosticResult:
        return check_srm_from_assignments(spec, df)

    def attrition_check(df: pd.DataFrame) -> DiagnosticResult:
        return check_attrition(spec, df, df, "revenue")

    return Scenario(
        service=service,
        design=_ready(design, service),
        data=data,
        estimator=DifferenceInMeans(
            TreatmentSpec(name="arm", control_value="control", treated_value="treatment")
        ),
        diagnostics=[
            DiagnosticStep("sample_ratio_mismatch", srm_check),
            DiagnosticStep("attrition", attrition_check),
        ],
    )


X = CovariateSpec(
    name="x",
    dtype=CovariateDType.NUMERIC,
    measurement_time="baseline",
    pre_treatment=TriState.TRUE,
    descendant_of_treatment=TriState.FALSE,
)


def observational(rng: np.random.Generator, *, n: int = 3000, strength: float = 1.0) -> Scenario:
    estimands, dags = _registries()
    estimands.register(
        Estimand(
            estimand_id="ate_y",
            type=EstimandType.ATE,
            treatment="treated",
            outcome="y",
            target_population=POP,
        )
    )
    dag = CausalDAG(
        name="obs",
        nodes=(DagNode(name="x"), DagNode(name="treated"), DagNode(name="y")),
        edges=(("x", "treated"), ("x", "y"), ("treated", "y")),
    )
    dags.register_dag(dag)
    adjustment = AdjustmentSet(
        dag_version=dag.version,
        treatment="treated",
        outcome="y",
        variables=frozenset({"x"}),
        rationale="x confounds treatment and outcome",
    )
    dags.register_adjustment_set(adjustment)
    service = AnalysisService(estimands, dags)
    design = StudyDesign(
        title="Programme effect",
        research_question="Does enrolment change the outcome?",
        design_family=DesignFamily.OBSERVATIONAL,
        target_population=POP,
        unit_of_analysis="unit_id",
        treatment="treated",
        outcome="y",
        assignment_mechanism="self-selection driven by x",
        time_zero="enrolment window",
        estimand_id="ate_y",
        dag_version=dag.version,
        adjustment_set_version=adjustment.version,
        interference_assessment="none expected",
        missingness_plan="complete case; outcome complete",
        overlap_expectations="enrolment observed across the range of x",
        inference_unit="unit_id",
        sensitivity_plan="trimming sweep and specification grid",
        primary_analysis="AIPW",
        assumptions=_justified(DesignFamily.OBSERVATIONAL),
    )
    x = rng.normal(size=n)
    t = rng.binomial(1, 1 / (1 + np.exp(-strength * x)))
    y = 1 + 3 * x + 2 * t + rng.normal(size=n)
    data = pd.DataFrame({"unit_id": np.arange(n), "treated": t, "x": x, "y": y})
    treatment = TreatmentSpec(name="treated")

    def overlap_check(df: pd.DataFrame) -> DiagnosticResult:
        ps = estimate_propensity(df, treatment, (X,))
        return check_overlap(ps, EstimandType.ATE)

    return Scenario(
        service=service,
        design=_ready(design, service),
        data=data,
        estimator=AIPWEstimator(treatment, (X,)),
        diagnostics=[DiagnosticStep("overlap", overlap_check)],
    )
