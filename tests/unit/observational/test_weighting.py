"""Task 3.5: weights normalize as documented; extreme weights are surfaced."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    Estimand,
    EstimandMismatchError,
    EstimandType,
    TargetPopulation,
    TreatmentSpec,
    TriState,
)
from causalimpact.estimators import run_estimator
from causalimpact.observational.overlap import OverlapRefusedError
from causalimpact.observational.weighting import (
    WeightingEstimator,
    WeightScheme,
    compute_weights,
    hajek_effect,
    normalized_weights,
    weight_diagnostics,
)

TREATMENT = TreatmentSpec(name="treated")
X = CovariateSpec(
    name="x",
    dtype=CovariateDType.NUMERIC,
    measurement_time="baseline",
    pre_treatment=TriState.TRUE,
    descendant_of_treatment=TriState.FALSE,
)
POP = TargetPopulation(name="cohort", description="Observational cohort")


def estimand(kind: EstimandType) -> Estimand:
    return Estimand(
        estimand_id=f"{kind.value.lower()}_y",
        type=kind,
        treatment="treated",
        outcome="y",
        target_population=POP,
    )


def dgp(
    rng: np.random.Generator, n: int = 2000, strength: float = 1.0, hetero: float = 1.0
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Confounded DGP: x raises both treatment probability and outcome.

    Effect tau(x) = 2 + hetero * x, so ATE, ATT, ATC and ATO differ when hetero != 0.
    The returned truths are the sample-level estimands given the true propensity.
    """
    x = rng.normal(size=n)
    e = 1 / (1 + np.exp(-(strength * x)))
    t = rng.binomial(1, e)
    tau = 2.0 + hetero * x
    y = 1.0 + 3.0 * x + tau * t + rng.normal(size=n)
    truth = {
        "ATE": float(np.mean(tau)),
        "ATT": float(np.sum(e * tau) / np.sum(e)),
        "ATC": float(np.sum((1 - e) * tau) / np.sum(1 - e)),
        "ATO": float(np.sum(e * (1 - e) * tau) / np.sum(e * (1 - e))),
    }
    return pd.DataFrame({"unit_id": np.arange(n), "treated": t, "x": x, "y": y}), truth


def estimator(scheme: WeightScheme, **kw: Any) -> WeightingEstimator:
    return WeightingEstimator(TREATMENT, (X,), scheme, seed=kw.pop("seed", 7), **kw)


class TestWeights:
    E = np.array([0.2, 0.5, 0.8, 0.4])
    T = np.array([1, 1, 0, 0], dtype=float)

    @pytest.mark.parametrize(
        ("scheme", "expected"),
        [
            (WeightScheme.IPW, [5.0, 2.0, 5.0, 1 / 0.6]),
            (WeightScheme.STABILIZED, [2.5, 1.0, 2.5, 0.5 / 0.6]),
            (WeightScheme.ATT, [1.0, 1.0, 4.0, 0.4 / 0.6]),
            (WeightScheme.ATC, [4.0, 1.0, 1.0, 1.0]),
            (WeightScheme.OVERLAP, [0.8, 0.5, 0.8, 0.4]),
        ],
    )
    def test_hand_computed_weights(self, scheme: WeightScheme, expected: list[float]) -> None:
        np.testing.assert_allclose(compute_weights(scheme, self.E, self.T), expected)

    def test_normalized_weights_sum_to_one_per_arm(self) -> None:
        w = normalized_weights(compute_weights(WeightScheme.IPW, self.E, self.T), self.T)
        assert w[self.T == 1].sum() == pytest.approx(1.0)
        assert w[self.T == 0].sum() == pytest.approx(1.0)

    def test_hajek_effect_hand_computed(self) -> None:
        y = np.array([10.0, 4.0, 3.0, 1.0])
        w = compute_weights(WeightScheme.IPW, self.E, self.T)
        treated = (5 * 10 + 2 * 4) / 7
        control = (5 * 3 + (1 / 0.6) * 1) / (5 + 1 / 0.6)
        assert hajek_effect(y, w, self.T) == pytest.approx(treated - control)

    def test_stabilized_weights_average_one_in_expectation(self, rng: np.random.Generator) -> None:
        data, _ = dgp(rng, n=50_000)
        e = 1 / (1 + np.exp(-data["x"].to_numpy()))
        w = compute_weights(WeightScheme.STABILIZED, e, data["treated"].to_numpy())
        t = data["treated"].to_numpy() == 1
        assert w[t].mean() == pytest.approx(1.0, abs=0.05)
        assert w[~t].mean() == pytest.approx(1.0, abs=0.05)

    def test_boundary_propensity_refused(self) -> None:
        with pytest.raises(ValueError, match="strictly inside"):
            compute_weights(WeightScheme.IPW, np.array([0.0, 0.5]), np.array([1, 0]))


def test_extreme_weights_surfaced() -> None:
    e = np.array([0.01] + [0.5] * 99)
    t = np.array([1] + [1] * 49 + [0] * 50, dtype=float)
    diag = weight_diagnostics(compute_weights(WeightScheme.IPW, e, t), t, WeightScheme.IPW)
    assert diag.status is DiagnosticStatus.WARNING
    assert diag.finding("extreme_weights").count == 1
    assert diag.metrics["treated"]["max_unit_share"] > 0.5  # type: ignore[index,call-overload,operator]


def test_estimate_records_scheme_estimand_and_diagnostics(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=800)
    est = estimator(WeightScheme.STABILIZED, n_bootstrap=60)
    out = run_estimator(est, data, estimand(EstimandType.ATE))
    assert out.estimand_type is EstimandType.ATE
    assert out.details["scheme"] == "stabilized"
    assert out.details["weights"]["estimand"] == "ATE"  # type: ignore[index,call-overload]
    assert str(out.details["propensity_fingerprint"]).startswith("sha256:")


def test_overlap_weights_cannot_be_reported_as_ate(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=300)
    with pytest.raises(EstimandMismatchError, match="cannot target ATE"):
        run_estimator(estimator(WeightScheme.OVERLAP), data, estimand(EstimandType.ATE))


def test_poor_overlap_refuses_ipw_but_overlap_weights_still_run(
    rng: np.random.Generator,
) -> None:
    data, _ = dgp(rng, n=1500, strength=6.0)
    with pytest.raises(OverlapRefusedError):
        run_estimator(estimator(WeightScheme.IPW, n_bootstrap=50), data, estimand(EstimandType.ATE))
    out = run_estimator(
        estimator(WeightScheme.OVERLAP, n_bootstrap=50), data, estimand(EstimandType.ATO)
    )
    assert out.estimand_type is EstimandType.ATO


def test_seeded_bootstrap_is_reproducible(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=500)
    target = estimand(EstimandType.ATE)
    a = run_estimator(estimator(WeightScheme.IPW, n_bootstrap=60), data, target)
    b = run_estimator(estimator(WeightScheme.IPW, n_bootstrap=60), data, target)
    c = run_estimator(estimator(WeightScheme.IPW, n_bootstrap=60, seed=8), data, target)
    assert a.std_error == b.std_error
    assert a.std_error != c.std_error


@pytest.mark.simulation
@pytest.mark.parametrize(
    ("scheme", "kind"),
    [
        (WeightScheme.IPW, EstimandType.ATE),
        (WeightScheme.STABILIZED, EstimandType.ATE),
        (WeightScheme.ATT, EstimandType.ATT),
        (WeightScheme.ATC, EstimandType.ATC),
        (WeightScheme.OVERLAP, EstimandType.ATO),
    ],
)
def test_each_scheme_recovers_its_own_estimand(
    rng: np.random.Generator, scheme: WeightScheme, kind: EstimandType
) -> None:
    sims = 60
    errors, naive_errors = [], []
    for _ in range(sims):
        data, truth = dgp(rng, n=3000)
        est = estimator(scheme, n_bootstrap=50)
        errors.append(run_estimator(est, data, estimand(kind)).estimate - truth[kind.value])
        y, t = data["y"], data["treated"] == 1
        naive_errors.append(y[t].mean() - y[~t].mean() - truth[kind.value])
    bias = float(np.mean(errors))
    mc_se = float(np.std(errors, ddof=1) / np.sqrt(sims))
    assert abs(bias) < 4 * mc_se + 0.02
    assert abs(np.mean(naive_errors)) > 1.0  # the confounding is real
