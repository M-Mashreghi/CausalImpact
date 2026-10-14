"""Task 1.4: estimand registry round-trips and estimand/output contract enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd
import pytest
from pydantic import ValidationError

from causalimpact.domain import (
    DomainError,
    EffectEstimate,
    Estimand,
    EstimandMismatchError,
    EstimandRegistry,
    EstimandType,
    TargetPopulation,
    TreatmentBasis,
    check_estimate_targets,
)
from causalimpact.estimators import run_estimator

POP = TargetPopulation(name="adults", description="Adults enrolled in 2025")


def estimand(kind: EstimandType = EstimandType.ATE, **kw: Any) -> Estimand:
    fields: dict[str, Any] = {
        "estimand_id": f"{kind.value.lower()}_y",
        "type": kind,
        "treatment": "t",
        "outcome": "y",
        "target_population": POP,
    }
    if kind is EstimandType.ITT:
        fields["treatment_basis"] = TreatmentBasis.ASSIGNMENT
    if kind is EstimandType.CATE:
        fields["conditioning_variables"] = ("age_band",)
    fields.update(kw)
    return Estimand(**fields)


def output(target: Estimand, **kw: Any) -> EffectEstimate:
    fields: dict[str, Any] = {
        "estimand_id": target.estimand_id,
        "estimand_type": target.type,
        "estimator": "toy",
        "estimate": 1.0,
        "std_error": 0.5,
        "ci_lower": 0.02,
        "ci_upper": 1.98,
        "confidence_level": 0.95,
        "inference_method": "normal_approximation",
        "n_units": 100,
    }
    if target.type is EstimandType.CATE:
        fields["conditioning_values"] = {"age_band": "30-39"}
    fields.update(kw)
    return EffectEstimate(**fields)


ALL_ESTIMANDS = [estimand(k) for k in EstimandType]


class TestEstimandDefinition:
    @pytest.mark.parametrize("target", ALL_ESTIMANDS, ids=lambda e: e.type.value)
    def test_every_type_round_trips(self, target: Estimand) -> None:
        assert Estimand.model_validate_json(target.model_dump_json()) == target
        assert target.target_population == POP
        assert target.averaged_over

    def test_cate_requires_conditioning(self) -> None:
        with pytest.raises(ValidationError, match="conditioning variable"):
            estimand(EstimandType.CATE, conditioning_variables=())

    @pytest.mark.parametrize("kind", [EstimandType.ATE, EstimandType.ATT, EstimandType.ITT])
    def test_non_cate_rejects_conditioning(self, kind: EstimandType) -> None:
        with pytest.raises(ValidationError, match="does not take conditioning"):
            estimand(kind, conditioning_variables=("age_band",))

    def test_itt_must_be_on_assignment(self) -> None:
        with pytest.raises(ValidationError, match="assignment"):
            estimand(EstimandType.ITT, treatment_basis=TreatmentBasis.RECEIPT)

    @pytest.mark.parametrize("var", ["t", "y"])
    def test_cate_cannot_condition_on_treatment_or_outcome(self, var: str) -> None:
        with pytest.raises(ValidationError, match="conditioning variable"):
            estimand(EstimandType.CATE, conditioning_variables=(var,))

    def test_att_and_atc_average_over_different_units(self) -> None:
        att, atc = estimand(EstimandType.ATT), estimand(EstimandType.ATC)
        assert att.averaged_over != atc.averaged_over


class TestRegistry:
    def test_registry_round_trips(self) -> None:
        registry = EstimandRegistry(ALL_ESTIMANDS)
        restored = EstimandRegistry.from_json(registry.to_json())
        assert list(restored) == list(registry)
        assert len(restored) == len(EstimandType)
        assert restored.to_json() == registry.to_json()

    def test_identical_reregistration_is_idempotent(self) -> None:
        registry = EstimandRegistry([estimand()])
        registry.register(estimand())
        assert len(registry) == 1

    def test_redefinition_under_same_id_refused(self) -> None:
        registry = EstimandRegistry([estimand()])
        with pytest.raises(DomainError, match="already registered"):
            registry.register(estimand(type=EstimandType.ATT))

    def test_unknown_lookup_fails(self) -> None:
        with pytest.raises(DomainError, match="unknown estimand"):
            EstimandRegistry().get("nope")


class TestOutputContract:
    @pytest.mark.parametrize("target", ALL_ESTIMANDS, ids=lambda e: e.type.value)
    def test_matching_output_accepted(self, target: Estimand) -> None:
        out = output(target)
        assert check_estimate_targets(target, out) is out

    def test_output_must_declare_estimand(self) -> None:
        fields = output(estimand()).model_dump()
        del fields["estimand_id"]
        with pytest.raises(ValidationError, match="estimand_id"):
            EffectEstimate(**fields)

    def test_mismatched_type_fails(self) -> None:
        ate = estimand()
        with pytest.raises(EstimandMismatchError, match="type ATT != ATE"):
            check_estimate_targets(ate, output(ate, estimand_type=EstimandType.ATT))

    def test_mismatched_id_fails(self) -> None:
        ate = estimand()
        with pytest.raises(EstimandMismatchError, match="expected 'ate_y'"):
            check_estimate_targets(ate, output(ate, estimand_id="ate_other"))

    def test_cate_output_must_match_conditioning(self) -> None:
        cate = estimand(EstimandType.CATE)
        with pytest.raises(EstimandMismatchError, match="condition on exactly"):
            check_estimate_targets(cate, output(cate, conditioning_values={"region": "EU"}))

    def test_marginal_output_cannot_be_conditional(self) -> None:
        ate = estimand()
        with pytest.raises(EstimandMismatchError, match="must not carry conditioning"):
            check_estimate_targets(ate, output(ate, conditioning_values={"age_band": "x"}))

    @pytest.mark.parametrize(
        "bad",
        [
            {"estimate": 5.0},
            {"std_error": -1.0},
            {"estimate": float("nan")},
            {"ci_upper": float("inf")},
            {"confidence_level": 1.0},
            {"n_units": 0},
            {"n_treated": 80, "n_control": 30},
        ],
    )
    def test_output_numerical_sanity(self, bad: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            output(estimand(), **bad)


@dataclass
class ToyEstimator:
    """Test double: returns a fixed output, optionally declaring the wrong estimand."""

    supported_estimands: frozenset[EstimandType]
    declared_type: EstimandType | None = None
    name: str = "toy"
    calls: list[str] = field(default_factory=list)

    def estimate(
        self, data: pd.DataFrame, estimand: Estimand, *, confidence_level: float
    ) -> EffectEstimate:
        self.calls.append(estimand.estimand_id)
        return output(
            estimand,
            estimand_type=self.declared_type or estimand.type,
            confidence_level=confidence_level,
        )


class TestRunEstimator:
    def test_supported_estimand_runs(self) -> None:
        est = ToyEstimator(frozenset({EstimandType.ATE}))
        result = run_estimator(est, pd.DataFrame(), estimand())
        assert result.estimand_type is EstimandType.ATE

    def test_unsupported_estimand_refused_before_fitting(self) -> None:
        est = ToyEstimator(frozenset({EstimandType.ATE}))
        with pytest.raises(EstimandMismatchError, match="cannot target ATT"):
            run_estimator(est, pd.DataFrame(), estimand(EstimandType.ATT))
        assert est.calls == []

    def test_silent_estimand_switch_detected(self) -> None:
        est = ToyEstimator(frozenset({EstimandType.ATT}), declared_type=EstimandType.ATE)
        with pytest.raises(EstimandMismatchError, match="type ATE != ATT"):
            run_estimator(est, pd.DataFrame(), estimand(EstimandType.ATT))
