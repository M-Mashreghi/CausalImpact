"""Task 2.2: known balanced / unbalanced fixtures classify correctly."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.experiments import Arm, ExperimentSpec
from causalimpact.experiments.srm import check_srm, check_srm_from_assignments


def spec(*allocations: tuple[str, float]) -> ExperimentSpec:
    allocations = allocations or (("control", 0.5), ("treatment", 0.5))
    return ExperimentSpec(
        experiment_id="exp",
        arms=tuple(Arm(name=n, allocation=a) for n, a in allocations),
        control_arm=allocations[0][0],
        randomization_unit="user_id",
        analysis_unit="user_id",
        primary_metric="y",
    )


@pytest.mark.parametrize(
    ("counts", "expected_status"),
    [
        ({"control": 5000, "treatment": 5000}, DiagnosticStatus.PASS),
        ({"control": 5000, "treatment": 5300}, DiagnosticStatus.PASS),  # p ~ 0.003
        ({"control": 5000, "treatment": 5500}, DiagnosticStatus.BLOCKING),  # p ~ 1e-6
        ({"control": 10000, "treatment": 9000}, DiagnosticStatus.BLOCKING),
    ],
)
def test_two_arm_fixtures(counts: dict[str, int], expected_status: DiagnosticStatus) -> None:
    assert check_srm(spec(), counts).status is expected_status


def test_matches_hand_computed_chi_square() -> None:
    result = check_srm(spec(), {"control": 5000, "treatment": 5500})
    # Expected 5250 each: chi2 = 2 * 250^2 / 5250
    assert result.metrics["statistic"] == pytest.approx(2 * 250**2 / 5250)
    # With 1 degree of freedom, P(chi2 > x) = erfc(sqrt(x / 2)): an independent reference.
    assert result.metrics["p_value"] == pytest.approx(math.erfc(math.sqrt(2 * 250**2 / 5250 / 2)))
    assert result.metrics["method"] == "chi_square"
    assert result.finding("srm_detected").examples == ("control",)
    assert any("triage" in n for n in result.notes)


def test_unequal_allocation_respected() -> None:
    s = spec(("control", 0.2), ("treatment", 0.8))
    assert check_srm(s, {"control": 2000, "treatment": 8000}).status is DiagnosticStatus.PASS
    assert check_srm(s, {"control": 5000, "treatment": 5000}).is_blocking


def test_three_arms() -> None:
    s = spec(("control", 0.5), ("a", 0.25), ("b", 0.25))
    assert not check_srm(s, {"control": 5010, "a": 2490, "b": 2500}).is_blocking
    assert check_srm(s, {"control": 5000, "a": 2000, "b": 3000}).is_blocking


def test_missing_arm_counts_as_zero() -> None:
    result = check_srm(spec(), {"control": 400})
    assert result.is_blocking
    assert result.metrics["observed"] == {"control": 400, "treatment": 0}


def test_small_two_arm_sample_uses_exact_binomial() -> None:
    result = check_srm(spec(), {"control": 3, "treatment": 4})
    assert result.metrics["method"] == "exact_binomial"
    assert result.metrics["p_value"] == pytest.approx(1.0)
    assert result.status is DiagnosticStatus.PASS


def test_small_multi_arm_sample_is_flagged_unreliable() -> None:
    s = spec(("control", 0.5), ("a", 0.25), ("b", 0.25))
    result = check_srm(s, {"control": 6, "a": 3, "b": 3})
    assert "srm_test_unreliable" in result.codes()
    assert result.status is DiagnosticStatus.WARNING


def test_no_units_blocks() -> None:
    assert check_srm(spec(), {}).codes() == {"no_units"}


@pytest.mark.parametrize(
    ("counts", "msg"),
    [({"control": 1, "other": 2}, "not in the design"), ({"control": -1}, "non-negative")],
)
def test_invalid_counts_rejected(counts: dict[str, int], msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        check_srm(spec(), counts)


def test_from_assignments_counts_unique_units() -> None:
    assignments = pd.DataFrame(
        {
            "user_id": ["a", "a", "b", "c", "d"],
            "arm": ["control", "control", "treatment", "control", "treatment"],
        }
    )
    result = check_srm_from_assignments(spec(), assignments)
    assert result.metrics["observed"] == {"control": 2, "treatment": 2}


@pytest.mark.simulation
def test_false_positive_rate_matches_alpha_under_correct_allocation(
    rng: np.random.Generator,
) -> None:
    s = spec(("control", 0.3), ("treatment", 0.7))
    sims, alpha = 2000, 0.05
    flagged = sum(
        check_srm(s, {"control": int(c), "treatment": 10_000 - int(c)}, alpha=alpha).is_blocking
        for c in rng.binomial(10_000, 0.3, size=sims)
    )
    assert 0.035 <= flagged / sims <= 0.065


@pytest.mark.simulation
def test_power_against_logging_loss(rng: np.random.Generator) -> None:
    # 5% of treatment units silently lost in logging on 100k users -> reliably detected.
    s = spec()
    hits = 0
    for _ in range(200):
        control = rng.binomial(100_000, 0.5)
        treatment = rng.binomial(100_000 - control, 0.95)
        hits += check_srm(s, {"control": int(control), "treatment": int(treatment)}).is_blocking
    assert hits / 200 > 0.95
