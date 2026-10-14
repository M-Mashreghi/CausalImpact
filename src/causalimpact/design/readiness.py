"""AnalysisReady validation (DESIGN_PROTOCOL.md).

``DesignReadinessValidator`` is a ``ReadinessCheck`` for ``StudyDesign.transition``. It
fails closed: every missing identification field, unknown reference, undeclared or
unjustified required assumption, or unsafe adjustment set is reported as a blocking
problem, and the design cannot become AnalysisReady until the list is empty.
"""

from __future__ import annotations

from dataclasses import dataclass

from causalimpact.dags import DagRegistry, assess_adjustment_set
from causalimpact.design.assumption_catalog import required_assumption_keys
from causalimpact.domain.assumptions import AssumptionStatus
from causalimpact.domain.estimands import EstimandRegistry, EstimandType
from causalimpact.domain.study_design import DesignFamily, StudyDesign

COMMON_REQUIRED_FIELDS = (
    "assignment_mechanism",
    "time_zero",
    "estimand_id",
    "interference_assessment",
    "missingness_plan",
    "inference_unit",
    "sensitivity_plan",
    "primary_analysis",
)

FAMILY_REQUIRED_FIELDS: dict[DesignFamily, tuple[str, ...]] = {
    DesignFamily.RANDOMIZED_EXPERIMENT: ("randomization_unit",),
    DesignFamily.OBSERVATIONAL: ("dag_version", "adjustment_set_version", "overlap_expectations"),
    DesignFamily.PANEL: (),
}


@dataclass(frozen=True)
class DesignReadinessValidator:
    estimands: EstimandRegistry
    dags: DagRegistry

    def __call__(self, design: StudyDesign) -> list[str]:
        problems: list[str] = []
        required = COMMON_REQUIRED_FIELDS + FAMILY_REQUIRED_FIELDS[design.design_family]
        for name in required:
            if getattr(design, name) is None:
                problems.append(f"missing required field: {name}")
        problems += self._assumption_problems(design)
        problems += self._estimand_problems(design)
        problems += self._dag_problems(design)
        problems += self._family_problems(design)
        return problems

    def _assumption_problems(self, design: StudyDesign) -> list[str]:
        problems: list[str] = []
        declared = {a.key: a for a in design.assumptions}
        for key in sorted(required_assumption_keys(design.design_family) - declared.keys()):
            problems.append(f"required assumption not declared: {key}")
        for assumption in design.assumptions:
            if assumption.justification is None:
                problems.append(f"assumption lacks a justification: {assumption.key}")
            if assumption.status is AssumptionStatus.VIOLATED:
                problems.append(f"assumption marked violated: {assumption.key}")
        return problems

    def _estimand_problems(self, design: StudyDesign) -> list[str]:
        if design.estimand_id is None:
            return []
        if design.estimand_id not in self.estimands:
            return [f"estimand not registered: {design.estimand_id}"]
        estimand = self.estimands.get(design.estimand_id)
        problems: list[str] = []
        if estimand.treatment != design.treatment:
            problems.append(
                f"estimand treatment {estimand.treatment!r} != design treatment "
                f"{design.treatment!r}"
            )
        if estimand.outcome != design.outcome:
            problems.append(
                f"estimand outcome {estimand.outcome!r} != design outcome {design.outcome!r}"
            )
        if estimand.target_population != design.target_population:
            problems.append("estimand target population differs from the design's")
        if (
            estimand.type is EstimandType.ITT
            and design.design_family is not DesignFamily.RANDOMIZED_EXPERIMENT
        ):
            problems.append("ITT requires a randomized assignment mechanism")
        return problems

    def _dag_problems(self, design: StudyDesign) -> list[str]:
        problems: list[str] = []
        if design.adjustment_set_version is not None and design.dag_version is None:
            problems.append("adjustment_set_version given without dag_version")
        if design.dag_version is None:
            return problems
        try:
            dag = self.dags.dag(design.dag_version)
        except KeyError:
            return [*problems, f"DAG not registered: {design.dag_version}"]
        for role in (design.treatment, design.outcome):
            if role not in dag.node_names:
                problems.append(f"DAG {dag.version} has no node {role!r}")
        if design.adjustment_set_version is None or problems:
            return problems
        try:
            adjustment = self.dags.adjustment_set(design.adjustment_set_version)
        except KeyError:
            return [f"adjustment set not registered: {design.adjustment_set_version}"]
        if adjustment.dag_version != dag.version:
            return [f"adjustment set belongs to {adjustment.dag_version}, not {dag.version}"]
        if (adjustment.treatment, adjustment.outcome) != (design.treatment, design.outcome):
            problems.append("adjustment set was built for a different treatment/outcome")
        assessment = assess_adjustment_set(dag, adjustment)
        for variable, flags in sorted(assessment.variable_flags.items()):
            if flags:
                joined = ", ".join(f.value for f in flags)
                problems.append(f"adjustment variable {variable!r} is unsafe: {joined}")
        if not assessment.satisfies_backdoor:
            problems.append("adjustment set does not satisfy the backdoor criterion in the DAG")
        if overlap := adjustment.variables & set(design.forbidden_post_treatment_variables):
            problems.append(f"adjustment set contains forbidden variables: {sorted(overlap)}")
        return problems

    def _family_problems(self, design: StudyDesign) -> list[str]:
        if design.design_family is not DesignFamily.RANDOMIZED_EXPERIMENT:
            return []
        if (
            design.randomization_unit is not None
            and design.randomization_unit != design.unit_of_analysis
            and design.cluster_variable is None
        ):
            return [
                f"randomization unit {design.randomization_unit!r} differs from analysis unit "
                f"{design.unit_of_analysis!r}; declare cluster_variable for valid inference"
            ]
        return []
