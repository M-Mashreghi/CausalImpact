"""Task 1.6: incomplete designs cannot become AnalysisReady; assumptions serialize."""

from __future__ import annotations

from typing import Any

import pytest

from causalimpact.dags import AdjustmentSet, CausalDAG, DagNode, DagRegistry
from causalimpact.design import (
    COMMON_REQUIRED_FIELDS,
    FAMILY_REQUIRED_FIELDS,
    DesignReadinessValidator,
    default_assumptions,
    required_assumption_keys,
)
from causalimpact.domain import (
    Assumption,
    AssumptionStatus,
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
from causalimpact.domain import Testability as AssumptionTestability

POP = TargetPopulation(name="members", description="Active members in 2025")

DAG = CausalDAG(
    name="membership",
    nodes=tuple(DagNode(name=n) for n in ("age", "tenure", "promo", "visits", "spend")),
    edges=(
        ("age", "promo"),
        ("age", "spend"),
        ("tenure", "promo"),
        ("tenure", "spend"),
        ("promo", "visits"),
        ("visits", "spend"),
        ("promo", "spend"),
    ),
)
SAFE_SET = AdjustmentSet(
    dag_version=DAG.version,
    treatment="promo",
    outcome="spend",
    variables=frozenset({"age", "tenure"}),
    rationale="age and tenure confound promo and spend",
)
MEDIATOR_SET = SAFE_SET.model_copy(update={"variables": frozenset({"age", "tenure", "visits"})})
PARTIAL_SET = SAFE_SET.model_copy(update={"variables": frozenset({"age"})})


def justified(family: DesignFamily) -> tuple[Assumption, ...]:
    return tuple(
        a.justify(f"documented rationale for {a.key}") for a in default_assumptions(family)
    )


def estimand(kind: EstimandType = EstimandType.ATE, **kw: Any) -> Estimand:
    fields: dict[str, Any] = {
        "estimand_id": f"{kind.value.lower()}_spend",
        "type": kind,
        "treatment": "promo",
        "outcome": "spend",
        "target_population": POP,
    }
    if kind is EstimandType.ITT:
        fields["treatment_basis"] = TreatmentBasis.ASSIGNMENT
    fields.update(kw)
    return Estimand(**fields)


@pytest.fixture
def validator() -> DesignReadinessValidator:
    dags = DagRegistry()
    dags.register_dag(DAG)
    for adj in (SAFE_SET, MEDIATOR_SET, PARTIAL_SET):
        dags.register_adjustment_set(adj)
    estimands = EstimandRegistry(
        [
            estimand(),
            estimand(EstimandType.ITT),
            estimand(EstimandType.ATE, estimand_id="other", outcome="visits"),
        ]
    )
    return DesignReadinessValidator(estimands=estimands, dags=dags)


def observational(**overrides: Any) -> StudyDesign:
    fields: dict[str, Any] = {
        "title": "Promo effect on spend",
        "research_question": "Does the promo increase 30-day spend?",
        "design_family": DesignFamily.OBSERVATIONAL,
        "target_population": POP,
        "unit_of_analysis": "member",
        "treatment": "promo",
        "outcome": "spend",
        "assignment_mechanism": "marketing targeting rules",
        "time_zero": "promo send date",
        "estimand_id": "ate_spend",
        "dag_version": DAG.version,
        "adjustment_set_version": SAFE_SET.version,
        "forbidden_post_treatment_variables": ("visits",),
        "interference_assessment": "members do not share accounts",
        "missingness_plan": "spend is complete from billing",
        "overlap_expectations": "promo sent across all tenure bands",
        "inference_unit": "member",
        "sensitivity_plan": "E-value style sensitivity and trimming sweep",
        "primary_analysis": "AIPW",
        "assumptions": justified(DesignFamily.OBSERVATIONAL),
    }
    fields.update(overrides)
    return StudyDesign(**fields)


def experiment(**overrides: Any) -> StudyDesign:
    fields: dict[str, Any] = {
        "design_family": DesignFamily.RANDOMIZED_EXPERIMENT,
        "estimand_id": "itt_spend",
        "randomization_unit": "member",
        "dag_version": None,
        "adjustment_set_version": None,
        "overlap_expectations": None,
        "assumptions": justified(DesignFamily.RANDOMIZED_EXPERIMENT),
    }
    fields.update(overrides)
    return observational(**fields)


def promote(design: StudyDesign, validator: DesignReadinessValidator) -> StudyDesign:
    validated = design.transition(DesignStatus.VALIDATED, reason="reviewed")
    return validated.transition(
        DesignStatus.ANALYSIS_READY, reason="ready", readiness_check=validator
    )


def problems(design: StudyDesign, validator: DesignReadinessValidator) -> str:
    found = validator(design)
    assert found, "expected the design to be blocked"
    with pytest.raises(DesignNotReadyError):
        promote(design, validator)
    return "\n".join(found)


class TestCompleteDesigns:
    def test_complete_observational_design_becomes_ready(
        self, validator: DesignReadinessValidator
    ) -> None:
        assert validator(observational()) == []
        assert promote(observational(), validator).status is DesignStatus.ANALYSIS_READY

    def test_complete_experiment_becomes_ready(self, validator: DesignReadinessValidator) -> None:
        assert validator(experiment()) == []

    def test_complete_panel_design_becomes_ready(self, validator: DesignReadinessValidator) -> None:
        panel = observational(
            design_family=DesignFamily.PANEL,
            assumptions=justified(DesignFamily.PANEL),
            dag_version=None,
            adjustment_set_version=None,
        )
        assert validator(panel) == []


class TestIncompleteDesigns:
    @pytest.mark.parametrize(
        "field",
        COMMON_REQUIRED_FIELDS + FAMILY_REQUIRED_FIELDS[DesignFamily.OBSERVATIONAL],
    )
    def test_missing_identification_field_blocks(
        self, validator: DesignReadinessValidator, field: str
    ) -> None:
        assert f"missing required field: {field}" in problems(
            observational(**{field: None}), validator
        )

    def test_experiment_requires_randomization_unit(
        self, validator: DesignReadinessValidator
    ) -> None:
        msg = problems(experiment(randomization_unit=None), validator)
        assert "randomization_unit" in msg

    @pytest.mark.parametrize("key", sorted(required_assumption_keys(DesignFamily.OBSERVATIONAL)))
    def test_undeclared_assumption_blocks(
        self, validator: DesignReadinessValidator, key: str
    ) -> None:
        kept = tuple(a for a in justified(DesignFamily.OBSERVATIONAL) if a.key != key)
        assert f"required assumption not declared: {key}" in problems(
            observational(assumptions=kept), validator
        )

    def test_unjustified_assumption_blocks(self, validator: DesignReadinessValidator) -> None:
        design = observational(assumptions=default_assumptions(DesignFamily.OBSERVATIONAL))
        assert "lacks a justification: positivity" in problems(design, validator)

    def test_violated_assumption_blocks(self, validator: DesignReadinessValidator) -> None:
        assumptions = tuple(
            a.model_copy(update={"status": AssumptionStatus.VIOLATED})
            if a.key == "positivity"
            else a
            for a in justified(DesignFamily.OBSERVATIONAL)
        )
        assert "violated: positivity" in problems(observational(assumptions=assumptions), validator)

    def test_unregistered_estimand_blocks(self, validator: DesignReadinessValidator) -> None:
        assert "estimand not registered" in problems(observational(estimand_id="nope"), validator)

    def test_estimand_outcome_mismatch_blocks(self, validator: DesignReadinessValidator) -> None:
        assert "estimand outcome" in problems(observational(estimand_id="other"), validator)

    def test_estimand_population_mismatch_blocks(self, validator: DesignReadinessValidator) -> None:
        other_pop = TargetPopulation(name="members", description="Only EU members")
        assert "target population" in problems(
            observational(target_population=other_pop), validator
        )

    def test_itt_requires_randomization(self, validator: DesignReadinessValidator) -> None:
        assert "ITT requires" in problems(observational(estimand_id="itt_spend"), validator)

    def test_mediator_in_adjustment_set_blocks(self, validator: DesignReadinessValidator) -> None:
        msg = problems(observational(adjustment_set_version=MEDIATOR_SET.version), validator)
        assert "'visits' is unsafe: mediator, descendant_of_treatment" in msg
        assert "forbidden variables: ['visits']" in msg

    def test_insufficient_adjustment_set_blocks(self, validator: DesignReadinessValidator) -> None:
        msg = problems(observational(adjustment_set_version=PARTIAL_SET.version), validator)
        assert "backdoor criterion" in msg

    def test_unregistered_dag_blocks(self, validator: DesignReadinessValidator) -> None:
        assert "DAG not registered" in problems(observational(dag_version="dag_x"), validator)

    def test_adjustment_without_dag_blocks(self, validator: DesignReadinessValidator) -> None:
        msg = problems(experiment(adjustment_set_version=SAFE_SET.version), validator)
        assert "without dag_version" in msg

    def test_cluster_randomization_requires_cluster_variable(
        self, validator: DesignReadinessValidator
    ) -> None:
        design = experiment(randomization_unit="household")
        assert "declare cluster_variable" in problems(design, validator)
        assert validator(experiment(randomization_unit="household", cluster_variable="hh")) == []

    def test_all_problems_reported_together(self, validator: DesignReadinessValidator) -> None:
        design = observational(time_zero=None, assumptions=(), estimand_id="nope")
        assert len(validator(design)) >= 1 + len(required_assumption_keys(design.design_family))


class TestAssumptions:
    @pytest.mark.parametrize("family", list(DesignFamily))
    def test_catalog_covers_each_family(self, family: DesignFamily) -> None:
        assumptions = default_assumptions(family)
        assert len(assumptions) >= 4
        assert all(a.status is AssumptionStatus.ASSUMED for a in assumptions)

    def test_key_identification_assumptions_are_untestable(self) -> None:
        obs = {a.key: a for a in default_assumptions(DesignFamily.OBSERVATIONAL)}
        panel = {a.key: a for a in default_assumptions(DesignFamily.PANEL)}
        assert obs["conditional_exchangeability"].testability is AssumptionTestability.UNTESTABLE
        assert panel["parallel_trends"].testability is AssumptionTestability.UNTESTABLE

    def test_no_proven_status_exists(self) -> None:
        assert {s.value for s in AssumptionStatus} == {
            "assumed",
            "diagnostic_support",
            "diagnostic_concern",
            "violated",
        }

    def test_assumptions_survive_serialization(self, validator: DesignReadinessValidator) -> None:
        ready = promote(observational(), validator)
        restored = StudyDesign.model_validate_json(ready.model_dump_json())
        assert restored.assumptions == ready.assumptions
        assert restored == ready

    def test_duplicate_assumption_keys_rejected(self) -> None:
        a = justified(DesignFamily.OBSERVATIONAL)
        with pytest.raises(ValueError, match="unique"):
            observational(assumptions=(*a, a[0]))
