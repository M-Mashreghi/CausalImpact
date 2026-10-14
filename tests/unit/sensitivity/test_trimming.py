"""Task 5.3: restricted sample / estimand metadata updates correctly."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from causalimpact.domain import EstimandType
from causalimpact.estimators import Estimator
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.observational.propensity import estimate_propensity
from causalimpact.observational.weighting import (
    WeightingEstimator,
    WeightScheme,
    truncate_weights,
)
from causalimpact.sensitivity.trimming import (
    PolicyKind,
    TrimmingPolicy,
    TrimmingReport,
    run_trimming_sensitivity,
    trimmed_estimand,
)
from tests.unit.observational.test_weighting import TREATMENT, X, dgp, estimand

DECLARED = datetime(2026, 1, 1, tzinfo=UTC)
RUN = datetime(2026, 2, 1, tzinfo=UTC)
ATE = estimand(EstimandType.ATE)
POLICIES = (
    TrimmingPolicy(kind=PolicyKind.NONE),
    TrimmingPolicy(kind=PolicyKind.PROPENSITY_TRIM, alpha=0.05),
    TrimmingPolicy(kind=PolicyKind.PROPENSITY_TRIM, alpha=0.1),
    TrimmingPolicy(kind=PolicyKind.WEIGHT_TRUNCATION, quantile=0.95),
)
IPW = WeightingEstimator(TREATMENT, (X,), WeightScheme.IPW, seed=2, n_bootstrap=50)


def run(data: pd.DataFrame, estimator: Estimator = IPW) -> TrimmingReport:
    return run_trimming_sensitivity(
        data, TREATMENT, (X,), ATE, estimator, POLICIES, declared_at=DECLARED, run_at=RUN
    )


def test_trimmed_estimand_records_restriction() -> None:
    derived = trimmed_estimand(ATE, 0.1)
    assert derived.estimand_id == "ate_y__trim_0.1"
    assert derived.type is EstimandType.ATE
    assert "estimated propensity in [0.1, 0.9]" in derived.target_population.inclusion_criteria
    assert ATE.target_population.inclusion_criteria == ()  # original untouched


def test_restricted_sample_metadata(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=2000, strength=2.0)
    report = run(data)
    by_label = {o.policy.label: o for o in report.outcomes}
    assert list(by_label) == ["none", "trim_0.05", "trim_0.1", "truncate_q0.95"]

    e = estimate_propensity(data, TREATMENT, (X,)).scores
    trim = by_label["trim_0.1"]
    expected_kept = int(((e >= 0.1) & (e <= 0.9)).sum())
    assert trim.n_units == expected_kept
    assert trim.n_dropped == len(data) - expected_kept
    assert trim.n_dropped_treated + trim.n_dropped_control == trim.n_dropped
    assert trim.population_changed and trim.estimand.estimand_id == "ate_y__trim_0.1"
    assert trim.estimate is not None and trim.estimate.estimand_id == "ate_y__trim_0.1"
    assert trim.estimate.n_units == expected_kept

    trunc = by_label["truncate_q0.95"]
    assert not trunc.population_changed and trunc.estimand == ATE and trunc.n_dropped == 0
    assert trunc.estimate is not None
    assert trunc.estimate.details["truncation_quantile"] == 0.95
    assert "bias" in trunc.notes[0]

    assert by_label["trim_0.05"].n_dropped <= trim.n_dropped
    assert report.summary["n_policies"] == 4


def test_failures_are_recorded(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=1500, strength=6.0)
    report = run(data)
    none = next(o for o in report.outcomes if o.policy.kind is PolicyKind.NONE)
    assert none.estimate is None and "OverlapRefusedError" in str(none.error)
    assert len(report.outcomes) == 4


def test_truncation_requires_weighting_estimator(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=300)
    with pytest.raises(ValueError, match="weighting estimator"):
        run(data, AIPWEstimator(TREATMENT, (X,)))


def test_truncate_weights_caps_within_arm() -> None:
    w = np.array([1.0, 2.0, 3.0, 100.0, 1.0, 1.0, 1.0, 50.0])
    t = np.array([1, 1, 1, 1, 0, 0, 0, 0])
    out = truncate_weights(w, t, 0.75)
    assert out[3] == pytest.approx(np.quantile(w[:4], 0.75))
    assert out[7] == pytest.approx(np.quantile(w[4:], 0.75))
    assert np.all(out <= w)


def test_policy_validation() -> None:
    with pytest.raises(ValidationError, match="alpha"):
        TrimmingPolicy(kind=PolicyKind.PROPENSITY_TRIM)
    with pytest.raises(ValidationError, match="quantile"):
        TrimmingPolicy(kind=PolicyKind.WEIGHT_TRUNCATION)


def test_must_be_declared_before_run(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=200)
    with pytest.raises(ValueError, match="declared before"):
        run_trimming_sensitivity(
            data, TREATMENT, (X,), ATE, IPW, POLICIES, declared_at=RUN, run_at=DECLARED
        )
