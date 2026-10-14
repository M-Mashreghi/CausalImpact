"""Task 5.1: every configured specification appears in the output."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from causalimpact.domain import CovariateDType, CovariateSpec, EstimandType, TriState
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.observational.outcome_regression import OutcomeRegressionEstimator
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme
from causalimpact.sensitivity.specification import (
    SpecificationGrid,
    SpecificationVariant,
    SpecStatus,
    run_specifications,
)
from tests.unit.observational.test_weighting import TREATMENT, X, dgp, estimand

DECLARED = datetime(2026, 1, 1, tzinfo=UTC)
RUN = datetime(2026, 2, 1, tzinfo=UTC)
GHOST = CovariateSpec(
    name="not_in_data",
    dtype=CovariateDType.NUMERIC,
    measurement_time="baseline",
    pre_treatment=TriState.TRUE,
    descendant_of_treatment=TriState.FALSE,
)


def grid(*extra: SpecificationVariant) -> SpecificationGrid:
    variants = (
        SpecificationVariant("aipw", AIPWEstimator(TREATMENT, (X,)), "primary"),
        SpecificationVariant(
            "ipw", WeightingEstimator(TREATMENT, (X,), WeightScheme.IPW, seed=1, n_bootstrap=50)
        ),
        SpecificationVariant(
            "regression", OutcomeRegressionEstimator(TREATMENT, (X,), seed=1, n_bootstrap=50)
        ),
        SpecificationVariant(
            "overlap_weights",
            WeightingEstimator(TREATMENT, (X,), WeightScheme.OVERLAP, seed=1, n_bootstrap=50),
        ),
        SpecificationVariant("bad_covariate", AIPWEstimator(TREATMENT, (X, GHOST))),
        *extra,
    )
    return SpecificationGrid(variants=variants, primary="aipw", declared_at=DECLARED)


def test_every_declared_spec_is_reported_in_order(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=1500)
    report = run_specifications(grid(), data, estimand(EstimandType.ATE), run_at=RUN)
    assert [o.label for o in report.outcomes] == [
        "aipw",
        "ipw",
        "regression",
        "overlap_weights",
        "bad_covariate",
    ]
    status = {o.label: o.status for o in report.outcomes}
    assert status["aipw"] is SpecStatus.SUCCEEDED
    assert status["overlap_weights"] is SpecStatus.REFUSED  # ATO cannot answer an ATE question
    assert status["bad_covariate"] is SpecStatus.FAILED
    assert report.summary["n_declared"] == 5
    assert report.summary["n_succeeded"] == 3
    assert report.summary["primary_status"] == "succeeded"
    assert report.summary["share_same_sign_as_primary"] == 1.0


def test_failures_keep_their_reason(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=500)
    report = run_specifications(grid(), data, estimand(EstimandType.ATE), run_at=RUN)
    failed = next(o for o in report.outcomes if o.label == "bad_covariate")
    assert "not_in_data" in str(failed.error)
    assert failed.estimate is None


def test_poor_overlap_is_a_recorded_refusal(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=1500, strength=6.0)
    report = run_specifications(grid(), data, estimand(EstimandType.ATE), run_at=RUN)
    assert next(o for o in report.outcomes if o.label == "ipw").status is SpecStatus.REFUSED
    assert report.summary["n_declared"] == 5


def test_grid_must_be_declared_before_running(rng: np.random.Generator) -> None:
    data, _ = dgp(rng, n=200)
    with pytest.raises(ValueError, match="declared before"):
        run_specifications(
            grid(), data, estimand(EstimandType.ATE), run_at=DECLARED.replace(year=2025)
        )


def test_fingerprint_changes_when_grid_changes() -> None:
    extra = SpecificationVariant("aipw_again", AIPWEstimator(TREATMENT, (X,)))
    assert grid().fingerprint == grid().fingerprint
    assert grid(extra).fingerprint != grid().fingerprint


def test_grid_validation() -> None:
    v = SpecificationVariant("a", AIPWEstimator(TREATMENT, (X,)))
    with pytest.raises(ValueError, match="unique"):
        SpecificationGrid((v, v), primary="a", declared_at=DECLARED)
    with pytest.raises(ValueError, match="primary"):
        SpecificationGrid((v,), primary="b", declared_at=DECLARED)
