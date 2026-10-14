"""Task 5.4: subgroup definitions are versioned and reproducible."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from causalimpact.domain import CovariateDType, CovariateSpec, TriState
from causalimpact.experiments.decision import CorrectionMethod, adjust_p_values
from causalimpact.heterogeneity.subgroups import (
    SubgroupDefinition,
    SubgroupPlan,
    estimate_subgroups,
    subgroup_estimand,
)
from tests.unit.experiments.test_estimators import DIM, ITT

DECLARED = datetime(2026, 1, 1, tzinfo=UTC)
RUN = datetime(2026, 2, 1, tzinfo=UTC)


def cov(name: str, dtype: CovariateDType, pre: TriState = TriState.TRUE) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=dtype,
        measurement_time="pre-assignment",
        pre_treatment=pre,
        descendant_of_treatment=TriState.FALSE,
    )


COVS = (cov("device", CovariateDType.CATEGORICAL), cov("age", CovariateDType.NUMERIC))
PLAN = SubgroupPlan(
    subgroups=(
        SubgroupDefinition(name="mobile", variable="device", values=("mobile",)),
        SubgroupDefinition(name="desktop", variable="device", values=("desktop",)),
        SubgroupDefinition(name="tablet", variable="device", values=("tablet",)),
    ),
    declared_at=DECLARED,
)


def experiment(rng: np.random.Generator, n: int = 6000) -> pd.DataFrame:
    arm = rng.permutation(np.repeat(["control", "treatment"], n // 2))
    device = rng.choice(["mobile", "desktop", "tablet"], n)
    effect = pd.Series(device).map({"mobile": 1.0, "desktop": 0.0, "tablet": 0.5}).to_numpy()
    y = rng.normal(0, 1, n) + effect * (arm == "treatment")
    return pd.DataFrame({"arm": arm, "device": device, "age": rng.integers(18, 70, n), "y": y})


def test_only_declared_subgroups_with_derived_estimands(rng: np.random.Generator) -> None:
    data = experiment(rng)
    report = estimate_subgroups(PLAN, data, ITT, DIM, COVS, run_at=RUN)
    assert [r.name for r in report.results] == ["mobile", "desktop", "tablet"]
    assert sum(r.n_units for r in report.results) == len(data)
    mobile = report.results[0]
    assert mobile.estimand_id == "itt_y__sub_mobile"
    assert mobile.estimate is not None
    assert mobile.estimate.estimand_type is ITT.type
    assert mobile.estimate.estimate == pytest.approx(1.0, abs=0.15)


def test_multiplicity_adjustment_matches_reference(rng: np.random.Generator) -> None:
    report = estimate_subgroups(PLAN, experiment(rng), ITT, DIM, COVS, run_at=RUN)
    raw = [r.estimate.p_value for r in report.results if r.estimate]  # type: ignore[union-attr]
    expected = adjust_p_values(raw, CorrectionMethod.HOLM)  # type: ignore[arg-type]
    assert [r.adjusted_p_value for r in report.results] == pytest.approx(expected)


def test_homogeneity_test_detects_heterogeneity(rng: np.random.Generator) -> None:
    report = estimate_subgroups(PLAN, experiment(rng), ITT, DIM, COVS, run_at=RUN)
    assert report.homogeneity["tested"] is True
    assert report.homogeneity["p_value"] < 0.001  # type: ignore[operator]


def test_overlapping_subgroups_skip_q_test(rng: np.random.Generator) -> None:
    plan = SubgroupPlan(
        subgroups=(
            SubgroupDefinition(name="young", variable="age", upper=40),
            SubgroupDefinition(name="all_adults", variable="age", lower=18),
        ),
        declared_at=DECLARED,
    )
    report = estimate_subgroups(plan, experiment(rng), ITT, DIM, COVS, run_at=RUN)
    assert report.homogeneity["tested"] is False


def test_versioning_is_reproducible() -> None:
    same = SubgroupPlan(subgroups=PLAN.subgroups, declared_at=DECLARED)
    assert same.version == PLAN.version
    extra = SubgroupDefinition(name="old", variable="age", lower=60)
    assert SubgroupPlan(subgroups=(*PLAN.subgroups, extra), declared_at=DECLARED).version != (
        PLAN.version
    )


def test_post_treatment_subgroup_variable_refused(rng: np.random.Generator) -> None:
    covs = (cov("device", CovariateDType.CATEGORICAL, pre=TriState.FALSE), COVS[1])
    with pytest.raises(ValueError, match="pre-treatment"):
        estimate_subgroups(PLAN, experiment(rng), ITT, DIM, covs, run_at=RUN)


def test_plan_must_precede_estimation(rng: np.random.Generator) -> None:
    with pytest.raises(ValueError, match="declared before"):
        estimate_subgroups(
            PLAN, experiment(rng), ITT, DIM, COVS, run_at=datetime(2025, 1, 1, tzinfo=UTC)
        )


def test_failed_subgroup_is_recorded(rng: np.random.Generator) -> None:
    plan = SubgroupPlan(
        subgroups=(SubgroupDefinition(name="nobody", variable="device", values=("watch",)),),
        declared_at=DECLARED,
    )
    result = estimate_subgroups(plan, experiment(rng), ITT, DIM, COVS, run_at=RUN).results[0]
    assert result.estimate is None and result.error


def test_definition_validation() -> None:
    with pytest.raises(ValidationError, match="not both"):
        SubgroupDefinition(name="x", variable="age", values=(1,), lower=0)
    with pytest.raises(ValidationError, match="not both"):
        SubgroupDefinition(name="x", variable="age")
    assert subgroup_estimand(ITT, PLAN.subgroups[0]).target_population.inclusion_criteria == (
        "device in ['mobile']",
    )
