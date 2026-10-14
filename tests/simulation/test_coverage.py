"""Task 7.3: reference normal-means coverage is near nominal; regressions are gated."""

from __future__ import annotations

import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.estimators import Estimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.did import TwoPeriodDiD
from causalimpact.simulation.benchmark import BenchmarkCase, run_benchmark
from causalimpact.simulation.coverage import (
    CoverageGate,
    check_coverage,
    coverage_summary,
)
from causalimpact.simulation.dgp import RCTConfig
from tests.simulation.test_benchmark import ITT, dim

pytestmark = pytest.mark.simulation


def test_normal_means_reference_is_near_nominal() -> None:
    case = BenchmarkCase("normal_means", RCTConfig(n=400, effect=0.3), dim, ITT, "ITT")
    summary = coverage_summary(run_benchmark(case, n_replicates=600, seed=4))
    assert summary.coverage == pytest.approx(0.95, abs=3 * summary.coverage_mc_se + 0.005)
    assert summary.mean_width > 0
    assert check_coverage(summary).status is DiagnosticStatus.PASS


def test_ignoring_cluster_randomisation_is_blocked() -> None:
    """Unit-level SEs on cluster-randomised data under-cover; the gate must catch it."""
    config = RCTConfig(n=2000, cluster_size=50, cluster_sd=1.0, effect=0.3)
    case = BenchmarkCase("clustered_naive", config, dim, ITT, "ITT")
    summary = coverage_summary(run_benchmark(case, n_replicates=150, seed=5))
    gate = check_coverage(summary)
    assert summary.coverage < 0.8
    assert "severe_undercoverage" in gate.codes()


def test_regression_against_baseline_is_blocked() -> None:
    case = BenchmarkCase("normal_means", RCTConfig(n=400), dim, ITT, "ITT")
    good = coverage_summary(run_benchmark(case, n_replicates=200, seed=6))
    worse = good.model_copy(update={"coverage": good.coverage - 0.05})
    result = check_coverage(worse, CoverageGate(max_shortfall=0.2), baseline=good)
    assert result.codes() == {"coverage_regression"}


def test_failures_cannot_hide_undercoverage() -> None:
    case = BenchmarkCase("attrition", RCTConfig(n=300, attrition_treated=0.5), dim, ITT, "ITT")
    result = run_benchmark(case, n_replicates=5, seed=1)
    with pytest.raises(ValueError, match="undefined"):
        coverage_summary(result)
    summary = coverage_summary(
        run_benchmark(
            BenchmarkCase("ok", RCTConfig(n=300), dim, ITT, "ITT"), n_replicates=40, seed=1
        )
    ).model_copy(update={"failure_rate": 0.2})
    assert "high_failure_rate" in check_coverage(summary).codes()


def test_did_reference_coverage() -> None:
    """2x2 DiD on a panel DGP with unit effects covers the post-period ATT."""
    from causalimpact.domain import Estimand, EstimandType, TargetPopulation
    from causalimpact.simulation.dgp import PanelConfig

    att = Estimand(
        estimand_id="att",
        type=EstimandType.ATT,
        treatment="treatment_start",
        outcome="outcome",
        target_population=TargetPopulation(name="u", description="units"),
    )

    def did(_: int) -> Estimator:
        return TwoPeriodDiD(PanelSpec(), pre_period=1, post_period=2)

    config = PanelConfig(n_units=300, n_periods=2, cohorts=(2,), dynamic_effects=(1.5,))
    summary = coverage_summary(
        run_benchmark(
            BenchmarkCase("did", config, did, att, "ATT_post_average"), n_replicates=200, seed=7
        )
    )
    assert check_coverage(summary).status is DiagnosticStatus.PASS
