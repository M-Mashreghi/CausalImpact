"""Analyse an A/B test end to end: design -> diagnostics -> estimate -> report.

uv run python examples/ab_test.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from causalimpact.dags import DagRegistry
from causalimpact.design import DesignReadinessValidator, default_assumptions
from causalimpact.domain import (
    DesignFamily,
    DesignStatus,
    Estimand,
    EstimandRegistry,
    EstimandType,
    StudyDesign,
    TargetPopulation,
    TreatmentBasis,
    TreatmentSpec,
)
from causalimpact.experiments import Arm, ExperimentSpec
from causalimpact.reporting import build_report, render_markdown
from causalimpact.services import AnalysisService, DiagnosticsConfig, RunSpec, execute
from causalimpact.services.estimator_factory import DifferenceInMeansConfig

# 1. Your data: one row per user, assigned arm, outcome. (Synthetic here.)
rng = np.random.default_rng(0)
n = 4000
arm = np.where(rng.random(n) < 0.5, "treatment", "control")
data = pd.DataFrame(
    {
        "user_id": np.arange(n),
        "arm": arm,
        "revenue": rng.normal(10, 3, n) + 0.3 * (arm == "treatment"),
    }
)

# 2. Estimand first: what effect, on whom.
population = TargetPopulation(name="users", description="Users who reached checkout")
estimands, dags = EstimandRegistry(), DagRegistry()
estimands.register(
    Estimand(
        estimand_id="itt_revenue",
        type=EstimandType.ITT,
        treatment="arm",
        outcome="revenue",
        target_population=population,
        treatment_basis=TreatmentBasis.ASSIGNMENT,
    )
)

# 3. Study design, with every identification field and a justification per assumption.
design = StudyDesign(
    title="Checkout redesign",
    research_question="Does the new checkout increase revenue per user?",
    design_family=DesignFamily.RANDOMIZED_EXPERIMENT,
    target_population=population,
    unit_of_analysis="user_id",
    treatment="arm",
    outcome="revenue",
    assignment_mechanism="50/50 user-level hash bucketing",
    randomization_unit="user_id",
    time_zero="first checkout view",
    estimand_id="itt_revenue",
    interference_assessment="users do not share accounts",
    missingness_plan="revenue is complete from billing",
    inference_unit="user_id",
    sensitivity_plan="CUPED as robustness check",
    primary_analysis="difference in means",
    assumptions=tuple(
        a.justify("documented in the experiment brief")
        for a in default_assumptions(DesignFamily.RANDOMIZED_EXPERIMENT)
    ),
)
validator = DesignReadinessValidator(estimands, dags)
design = design.transition(DesignStatus.VALIDATED, reason="reviewed").transition(
    DesignStatus.ANALYSIS_READY, reason="ready", readiness_check=validator
)

# 4. Run: SRM and attrition checks first, then the estimator.
spec = RunSpec(
    estimator=DifferenceInMeansConfig(
        treatment=TreatmentSpec(name="arm", control_value="control", treated_value="treatment")
    ),
    diagnostics=DiagnosticsConfig(
        experiment=ExperimentSpec(
            experiment_id="checkout",
            arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
            control_arm="control",
            randomization_unit="user_id",
            analysis_unit="user_id",
            primary_metric="revenue",
        )
    ),
    seed=1,
)
result = execute(AnalysisService(estimands, dags), design, spec, data)

# 5. Assumption-aware report.
print(render_markdown(build_report(result)))
