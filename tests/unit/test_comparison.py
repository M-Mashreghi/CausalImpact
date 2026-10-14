"""Task 6.5: mismatched estimands trigger a block; compatible ones are grouped."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.domain import EstimandMismatchError, EstimandType
from causalimpact.estimators import run_estimator
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.observational.outcome_regression import OutcomeRegressionEstimator
from causalimpact.observational.weighting import WeightingEstimator, WeightScheme
from causalimpact.sensitivity.trimming import trimmed_estimand
from causalimpact.services.comparison import (
    LabelledEstimate,
    compare_estimates,
    ensure_comparable,
    incompatibilities,
)
from tests.unit.observational.test_weighting import TREATMENT, X, dgp, estimand

ATE = estimand(EstimandType.ATE)
ATT = estimand(EstimandType.ATT)


@pytest.fixture
def estimates(rng: np.random.Generator) -> dict[str, LabelledEstimate]:
    data, _ = dgp(rng, n=1500)
    out = {}
    for label, est, target in (
        ("aipw_ate", AIPWEstimator(TREATMENT, (X,)), ATE),
        ("reg_ate", OutcomeRegressionEstimator(TREATMENT, (X,), seed=1, n_bootstrap=50), ATE),
        ("aipw_att", AIPWEstimator(TREATMENT, (X,)), ATT),
        (
            "overlap_ato",
            WeightingEstimator(TREATMENT, (X,), WeightScheme.OVERLAP, seed=1, n_bootstrap=50),
            estimand(EstimandType.ATO),
        ),
    ):
        out[label] = LabelledEstimate(label, target, run_estimator(est, data, target))
    return out


def test_compatible_estimates_share_one_group(estimates: dict[str, LabelledEstimate]) -> None:
    report = compare_estimates([estimates["aipw_ate"], estimates["reg_ate"]])
    assert report.all_comparable
    assert not report.diagnostic.is_blocking
    members = report.groups[0].members
    assert [m["label"] for m in members] == ["aipw_ate", "reg_ate"]
    assert members[0]["difference_from_first"] == 0.0


def test_mismatched_estimands_block(estimates: dict[str, LabelledEstimate]) -> None:
    report = compare_estimates(list(estimates.values()))
    assert report.diagnostic.is_blocking
    assert len(report.groups) == 3  # ATE, ATT, ATO
    finding = report.diagnostic.finding("incompatible_estimands")
    assert any("aipw_att: type: ATE vs ATT" in e for e in finding.examples)


def test_no_ranking_input_order_is_kept(estimates: dict[str, LabelledEstimate]) -> None:
    order = [estimates["reg_ate"], estimates["aipw_ate"]]
    report = compare_estimates(order)
    assert [m["label"] for m in report.groups[0].members] == ["reg_ate", "aipw_ate"]
    assert "does not rank" in report.diagnostic.notes[0]


def test_population_restriction_is_incompatible(estimates: dict[str, LabelledEstimate]) -> None:
    trimmed = LabelledEstimate(
        "trimmed", trimmed_estimand(ATE, 0.1), estimates["aipw_ate"].estimate
    )
    reasons = incompatibilities(estimates["aipw_ate"], trimmed)
    assert any("target population" in r for r in reasons)
    with pytest.raises(EstimandMismatchError, match="different estimands"):
        ensure_comparable(estimates["aipw_ate"], trimmed)


def test_confidence_level_must_match(estimates: dict[str, LabelledEstimate]) -> None:
    item = estimates["aipw_ate"]
    other = LabelledEstimate(
        "ninety", ATE, item.estimate.model_copy(update={"confidence_level": 0.9})
    )
    assert "confidence levels differ" in incompatibilities(item, other)


def test_duplicate_labels_rejected(estimates: dict[str, LabelledEstimate]) -> None:
    with pytest.raises(ValueError, match="unique"):
        compare_estimates([estimates["aipw_ate"], estimates["aipw_ate"]])
