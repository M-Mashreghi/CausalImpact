"""Task 5.5: the report labels exploratory results correctly."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.heterogeneity.exploratory import (
    EvidenceLabel,
    ExplorationConfig,
    candidate_subgroups,
    explore_subgroups,
)
from tests.unit.experiments.test_estimators import DIM, ITT


def cov(name: str, dtype: CovariateDType, pre: TriState = TriState.TRUE) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="pre-assignment",
        pre_treatment=pre,
        descendant_of_treatment=TriState.FALSE,
    )


COVS = (
    cov("region", CovariateDType.CATEGORICAL),
    cov("plan", CovariateDType.CATEGORICAL),
    cov("age", CovariateDType.NUMERIC),
)


def experiment(rng: np.random.Generator, n: int = 8000, hetero: bool = False) -> pd.DataFrame:
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    region = rng.choice(list("abcdefgh"), n)
    plan = rng.choice(["free", "pro", "team", "enterprise"], n)
    effect = 0.2 + (0.6 * (region == "c") if hetero else 0.0)
    y = rng.normal(0, 1, n) + effect * (arm == "treatment")
    return pd.DataFrame(
        {"arm": arm, "region": region, "plan": plan, "age": rng.normal(40, 10, n), "y": y}
    )


def test_candidates_cover_levels_and_median_splits(rng: np.random.Generator) -> None:
    names = [c.name for c in candidate_subgroups(experiment(rng, n=500), COVS)]
    assert len(names) == 8 + 4 + 2
    assert "age<median" in names and "region=c" in names


def test_holdout_results_are_labelled_exploratory_validated(rng: np.random.Generator) -> None:
    report = explore_subgroups(experiment(rng), ITT, DIM, COVS, ExplorationConfig(seed=1))
    assert report.findings
    assert {f.label for f in report.findings} == {EvidenceLabel.EXPLORATORY_HOLDOUT_VALIDATED}
    assert all(f.label is not EvidenceLabel.CONFIRMATORY for f in report.findings)
    assert report.n_discovery + report.n_holdout == 8000
    assert "pre-specified" in report.findings[0].note


def test_without_holdout_results_are_unvalidated(rng: np.random.Generator) -> None:
    config = ExplorationConfig(seed=1, holdout_fraction=0.0)
    report = explore_subgroups(experiment(rng), ITT, DIM, COVS, config)
    assert {f.label for f in report.findings} == {EvidenceLabel.EXPLORATORY_UNVALIDATED}
    assert "hypothesis-generating" in report.findings[0].note


def test_true_heterogeneity_survives_the_holdout(rng: np.random.Generator) -> None:
    report = explore_subgroups(
        experiment(rng, n=20_000, hetero=True), ITT, DIM, COVS, ExplorationConfig(seed=3, top_k=1)
    )
    top = report.findings[0]
    assert top.subgroup == "region=c"
    assert top.reported_estimate is not None
    assert top.reported_estimate.estimate == pytest.approx(0.8, abs=0.15)
    assert top.adjusted_p_value is not None and top.adjusted_p_value < 0.01


def test_split_is_seeded(rng: np.random.Generator) -> None:
    data = experiment(rng, n=2000)
    a = explore_subgroups(data, ITT, DIM, COVS, ExplorationConfig(seed=5))
    b = explore_subgroups(data, ITT, DIM, COVS, ExplorationConfig(seed=5))
    assert a == b


def test_post_treatment_variable_refused(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="pre-treatment"):
        explore_subgroups(
            experiment(rng, n=500),
            ITT,
            DIM,
            (cov("region", CovariateDType.CATEGORICAL, pre=TriState.FALSE),),
            ExplorationConfig(seed=1),
        )


@pytest.mark.simulation
def test_holdout_removes_selection_bias_under_null(rng: np.random.Generator) -> None:
    """No true heterogeneity: the selected subgroup's discovery estimate is inflated,
    the holdout estimate is not."""
    sims, inflation_discovery, inflation_holdout = 40, [], []
    for i in range(sims):
        report = explore_subgroups(
            experiment(rng, n=6000), ITT, DIM, COVS, ExplorationConfig(seed=i, top_k=1)
        )
        top = report.findings[0]
        assert top.reported_estimate is not None
        inflation_discovery.append(abs(top.discovery_estimate - 0.2))
        inflation_holdout.append(abs(top.reported_estimate.estimate - 0.2))
    assert np.mean(inflation_discovery) > 1.5 * np.mean(inflation_holdout)
