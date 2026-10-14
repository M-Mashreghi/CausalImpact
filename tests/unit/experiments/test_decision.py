"""Task 2.8: correction methods match reference fixtures; decisions follow the policy."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from causalimpact.diagnostics import DiagnosticResult, Finding, FindingSeverity
from causalimpact.domain import EffectEstimate, EstimandType
from causalimpact.experiments import Arm, ExperimentSpec
from causalimpact.experiments.decision import (
    CorrectionMethod,
    Decision,
    DecisionLabel,
    DecisionPolicy,
    Direction,
    GuardrailRule,
    GuardrailStatus,
    adjust_p_values,
    decide,
    guardrail_status,
)

P = [0.01, 0.04, 0.03, 0.005]


class TestCorrections:
    # Reference values: R `p.adjust(c(0.01, 0.04, 0.03, 0.005), method = ...)`.
    @pytest.mark.parametrize(
        ("method", "expected"),
        [
            (CorrectionMethod.NONE, P),
            (CorrectionMethod.BONFERRONI, [0.04, 0.16, 0.12, 0.02]),
            (CorrectionMethod.HOLM, [0.03, 0.06, 0.06, 0.02]),
            (CorrectionMethod.BENJAMINI_HOCHBERG, [0.02, 0.04, 0.04, 0.02]),
        ],
    )
    def test_reference_fixture(self, method: CorrectionMethod, expected: list[float]) -> None:
        assert adjust_p_values(P, method) == pytest.approx(expected)

    def test_second_reference_with_ties_and_caps(self) -> None:
        # R: p.adjust(c(0.5, 0.01, 0.01, 0.9), "BH") -> 0.6667 0.02 0.02 0.9
        p = [0.5, 0.01, 0.01, 0.9]
        bh = adjust_p_values(p, CorrectionMethod.BENJAMINI_HOCHBERG)
        assert bh == pytest.approx([2 / 3, 0.02, 0.02, 0.9])
        # R: p.adjust(..., "holm") -> 1.00 0.04 0.04 1.00
        assert adjust_p_values(p, CorrectionMethod.HOLM) == pytest.approx([1.0, 0.04, 0.04, 1.0])

    def test_adjusted_never_below_raw(self) -> None:
        for method in CorrectionMethod:
            assert all(a >= r for a, r in zip(adjust_p_values(P, method), P, strict=True))

    def test_invalid_p_values(self) -> None:
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            adjust_p_values([0.2, 1.5], CorrectionMethod.HOLM)


SPEC = ExperimentSpec(
    experiment_id="exp",
    arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
    control_arm="control",
    randomization_unit="user_id",
    analysis_unit="user_id",
    primary_metric="conversion",
    secondary_metrics=("clicks", "time_on_site"),
    guardrail_metrics=("latency_ms",),
)
DECLARED = datetime(2026, 3, 1, tzinfo=UTC)
ANALYSED = datetime(2026, 3, 20, tzinfo=UTC)
POLICY = DecisionPolicy(
    experiment_id="exp",
    declared_at=DECLARED,
    guardrails=(
        GuardrailRule(
            metric="latency_ms", direction=Direction.DECREASE_IS_BETTER, max_degradation=20.0
        ),
    ),
)


def est(estimate: float, half_width: float, p: float | None = 0.5, **kw: Any) -> EffectEstimate:
    return EffectEstimate(
        estimand_id="itt",
        estimand_type=EstimandType.ITT,
        estimator="difference_in_means",
        estimate=estimate,
        std_error=half_width / 1.96,
        ci_lower=estimate - half_width,
        ci_upper=estimate + half_width,
        confidence_level=kw.pop("confidence_level", 0.95),
        inference_method="test",
        p_value=p,
        n_units=1000,
    )


def results(**overrides: EffectEstimate) -> dict[str, EffectEstimate]:
    base = {
        "conversion": est(0.02, 0.01, p=0.0001),
        "clicks": est(1.0, 0.9, p=0.03),
        "time_on_site": est(0.5, 1.0, p=0.32),
        "latency_ms": est(2.0, 5.0),
    }
    base.update(overrides)
    return base


def run(res: dict[str, EffectEstimate], trust: list[DiagnosticResult] | None = None) -> Decision:
    return decide(SPEC, POLICY, res, trust or [], analysed_at=ANALYSED)


class TestDecision:
    def test_ship_when_primary_wins_and_guardrails_clear(self) -> None:
        decision = run(results())
        assert decision.label is DecisionLabel.SHIP
        assert decision.guardrails == {"latency_ms": GuardrailStatus.CLEARED}
        assert decision.policy_fingerprint == POLICY.fingerprint

    def test_secondary_metrics_are_adjusted_but_do_not_drive_label(self) -> None:
        decision = run(results())
        clicks = decision.secondary[0]
        assert clicks["metric"] == "clicks"
        assert clicks["adjusted_p_value"] == pytest.approx(0.06)  # Holm over 2 metrics
        assert clicks["correction"] == "holm"

    def test_blocking_trust_diagnostic_blocks(self) -> None:
        srm = DiagnosticResult(
            name="sample_ratio_mismatch",
            findings=(
                Finding(code="srm_detected", severity=FindingSeverity.BLOCKING, message="x"),
            ),
        )
        decision = run(results(), [srm])
        assert decision.label is DecisionLabel.BLOCKED
        assert "sample_ratio_mismatch" in decision.reasons[0]

    def test_guardrail_violation_means_no_ship(self) -> None:
        decision = run(results(latency_ms=est(30.0, 10.0)))
        assert decision.label is DecisionLabel.NO_SHIP
        assert decision.guardrails["latency_ms"] is GuardrailStatus.VIOLATED

    def test_unresolved_guardrail_is_inconclusive(self) -> None:
        decision = run(results(latency_ms=est(5.0, 40.0)))
        assert decision.label is DecisionLabel.INCONCLUSIVE
        assert decision.guardrails["latency_ms"] is GuardrailStatus.UNRESOLVED

    def test_non_significant_primary_is_inconclusive(self) -> None:
        assert run(results(conversion=est(0.002, 0.01, p=0.7))).label is DecisionLabel.INCONCLUSIVE

    def test_significantly_worse_primary_is_no_ship(self) -> None:
        assert run(results(conversion=est(-0.02, 0.01, p=0.0001))).label is DecisionLabel.NO_SHIP

    def test_policy_must_precede_analysis(self) -> None:
        late = POLICY.model_copy(update={"declared_at": datetime(2026, 4, 1, tzinfo=UTC)})
        with pytest.raises(ValueError, match="declared before"):
            decide(SPEC, late, results(), [], analysed_at=ANALYSED)

    def test_every_guardrail_needs_a_rule(self) -> None:
        bare = POLICY.model_copy(update={"guardrails": ()})
        with pytest.raises(ValueError, match="guardrail metric"):
            decide(SPEC, bare, results(), [], analysed_at=ANALYSED)

    def test_missing_results_rejected(self) -> None:
        res = results()
        del res["clicks"]
        with pytest.raises(ValueError, match="missing results"):
            run(res)

    def test_confidence_level_must_match_alpha(self) -> None:
        with pytest.raises(ValueError, match="confidence level"):
            run(results(clicks=est(1.0, 0.9, p=0.03, confidence_level=0.9)))

    def test_policy_fingerprint_changes_with_policy(self) -> None:
        other = POLICY.model_copy(update={"secondary_correction": CorrectionMethod.BONFERRONI})
        assert other.fingerprint != POLICY.fingerprint

    def test_duplicate_guardrail_rules_rejected(self) -> None:
        rule = POLICY.guardrails[0]
        with pytest.raises(ValidationError, match="duplicate"):
            DecisionPolicy(experiment_id="exp", declared_at=DECLARED, guardrails=(rule, rule))


@pytest.mark.parametrize(
    ("direction", "estimate", "half", "expected"),
    [
        (Direction.INCREASE_IS_BETTER, -5.0, 2.0, GuardrailStatus.VIOLATED),
        (Direction.INCREASE_IS_BETTER, -1.0, 2.0, GuardrailStatus.CLEARED),
        (Direction.INCREASE_IS_BETTER, -1.0, 9.0, GuardrailStatus.UNRESOLVED),
        (Direction.DECREASE_IS_BETTER, 5.0, 2.0, GuardrailStatus.VIOLATED),
        (Direction.DECREASE_IS_BETTER, -3.0, 2.0, GuardrailStatus.CLEARED),
    ],
)
def test_guardrail_status_directions(
    direction: Direction, estimate: float, half: float, expected: GuardrailStatus
) -> None:
    rule = GuardrailRule(metric="m", direction=direction, max_degradation=5.0)
    assert guardrail_status(rule, est(estimate, half)) is expected
