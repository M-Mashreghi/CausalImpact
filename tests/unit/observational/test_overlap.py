"""Task 3.3: poor-overlap fixtures are flagged; good overlap passes."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.domain import EstimandType
from causalimpact.observational.overlap import (
    OverlapPolicy,
    OverlapRefusedError,
    check_overlap,
    ensure_overlap,
    estimand_weights,
    kish_ess,
)
from causalimpact.observational.propensity import PropensityScores


def scores(rng: np.random.Generator, n: int, strength: float) -> PropensityScores:
    """Propensity from logit = strength * x; larger strength means worse overlap."""
    x = rng.normal(size=n)
    e = 1 / (1 + np.exp(-strength * x))
    t = rng.binomial(1, e).astype(float)
    return PropensityScores(unit_ids=np.arange(n), treated=t, scores=e)


def test_good_overlap_passes(rng: np.random.Generator) -> None:
    result = check_overlap(scores(rng, 5000, 0.5), EstimandType.ATE)
    assert result.status is DiagnosticStatus.PASS
    assert result.metrics["n_violating"] == 0
    assert result.metrics["ess_fraction"]["treated"] > 0.8  # type: ignore[index,call-overload]


def test_poor_overlap_blocks(rng: np.random.Generator) -> None:
    result = check_overlap(scores(rng, 5000, 4.0), EstimandType.ATE)
    assert result.is_blocking
    assert "positivity_violation" in result.codes()
    with pytest.raises(OverlapRefusedError, match="insufficient"):
        ensure_overlap(result)


def test_att_only_needs_controls_for_treated(rng: np.random.Generator) -> None:
    # Many controls with tiny propensity (irrelevant for ATT) and no treated near 1.
    n = 4000
    e = np.concatenate([np.full(n // 2, 0.001), rng.uniform(0.2, 0.6, n // 2)])
    t = np.concatenate([np.zeros(n // 2), rng.binomial(1, 0.4, n // 2)])
    ps = PropensityScores(unit_ids=np.arange(n), treated=t, scores=e)
    assert check_overlap(ps, EstimandType.ATE).is_blocking
    att = check_overlap(ps, EstimandType.ATT)
    assert "positivity_violation" not in att.codes()
    assert att.metrics["n_relevant"] == int(t.sum())


def test_warning_band(rng: np.random.Generator) -> None:
    ps = scores(rng, 5000, 1.0)
    e = ps.scores.copy()
    e[:10] = 0.001  # 0.2% violating: warn, not block
    result = check_overlap(PropensityScores(ps.unit_ids, ps.treated, e), EstimandType.ATE)
    assert result.finding("positivity_violation").severity == "warning"


def test_plot_ready_and_policy_recorded(rng: np.random.Generator) -> None:
    policy = OverlapPolicy(epsilon=0.05, histogram_bins=10)
    result = check_overlap(scores(rng, 1000, 1.0), EstimandType.ATE, policy)
    treated = result.metrics["treated"]
    assert len(treated["histogram"]) == 10  # type: ignore[index,call-overload,arg-type]
    assert sum(treated["histogram"]) == treated["n"]  # type: ignore[index,call-overload,arg-type]
    assert len(result.metrics["histogram_bin_edges"]) == 11  # type: ignore[arg-type]
    assert result.metrics["policy"]["epsilon"] == 0.05  # type: ignore[index,call-overload]
    lo, hi = result.metrics["common_support"]  # type: ignore[misc]
    assert 0 < lo < hi < 1


def test_kish_ess_and_weights() -> None:
    assert kish_ess(np.ones(10)) == pytest.approx(10.0)
    assert kish_ess(np.array([1.0, 0.0, 0.0])) == pytest.approx(1.0)
    e, t = np.array([0.2, 0.5, 0.8]), np.array([1.0, 0.0, 1.0])
    np.testing.assert_allclose(estimand_weights(e, t, EstimandType.ATE), [5.0, 2.0, 1.25])
    np.testing.assert_allclose(estimand_weights(e, t, EstimandType.ATT), [1.0, 1.0, 1.0])
    np.testing.assert_allclose(estimand_weights(e, t, EstimandType.ATC), [4.0, 1.0, 0.25])


def test_unsupported_estimand(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="support"):
        check_overlap(scores(rng, 100, 1.0), EstimandType.ITT)


@pytest.mark.simulation
def test_severity_increases_monotonically_with_confounding_strength(
    rng: np.random.Generator,
) -> None:
    fractions = [
        check_overlap(scores(rng, 5000, s), EstimandType.ATE).metrics["violation_fraction"]
        for s in (0.5, 2.0, 3.0, 5.0)
    ]
    assert fractions == sorted(fractions)  # type: ignore[type-var]
    assert fractions[0] == 0.0 and fractions[-1] > 0.05  # type: ignore[operator]
