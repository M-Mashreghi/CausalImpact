"""Task 4.6: clustered DGP standard errors differ from naive ones as expected."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from causalimpact.diagnostics import DiagnosticStatus
from causalimpact.estimators import run_estimator
from causalimpact.estimators.clustering import (
    ClusterInferenceError,
    ClusterPolicy,
    check_clusters,
)
from causalimpact.estimators.ols import ols_cluster_robust
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.did import TwoPeriodDiD
from causalimpact.panel.event_study import twfe_event_study
from tests.unit.panel.test_did import ATT

NAIVE = TwoPeriodDiD(PanelSpec(), pre_period=1, post_period=2)
CLUSTERED = TwoPeriodDiD(PanelSpec(cluster="state"), pre_period=1, post_period=2)


def state_panel(
    rng: np.random.Generator, n_states: int = 40, per_state: int = 50, effect: float = 1.0
) -> pd.DataFrame:
    """Treatment assigned by state; state-level post-period shocks correlate units."""
    treated_state = rng.permutation(np.arange(n_states) < n_states // 2)
    shock = rng.normal(0, 1.0, n_states)  # common post-period shock per state
    rows = []
    for s in range(n_states):
        for j in range(per_state):
            level = rng.normal()
            for t in (1, 2):
                y = level + 0.5 * (t == 2) + rng.normal(0, 0.5)
                if t == 2:
                    y += shock[s] + effect * treated_state[s]
                rows.append(
                    {
                        "unit_id": f"{s}_{j}",
                        "state": s,
                        "period": t,
                        "treatment_start": 2.0 if treated_state[s] else np.nan,
                        "outcome": y,
                    }
                )
    return pd.DataFrame(rows)


def test_cr1_matches_hand_computation() -> None:
    x = np.column_stack([np.ones(4), [0.0, 1.0, 0.0, 1.0]])
    y = np.array([1.0, 3.0, 2.0, 6.0])
    clusters = np.array([0, 0, 1, 1])
    fit = ols_cluster_robust(x, y, clusters)
    xtx_inv = np.linalg.inv(x.T @ x)
    e = y - x @ fit.coef
    meat = sum(
        np.outer(x[clusters == g].T @ e[clusters == g], x[clusters == g].T @ e[clusters == g])
        for g in (0, 1)
    )
    expected = 2 / 1 * 3 / 2 * xtx_inv @ meat @ xtx_inv
    np.testing.assert_allclose(fit.cov, expected)


def test_clustered_se_exceeds_naive_se(rng: np.random.Generator) -> None:
    data = state_panel(rng)
    naive = run_estimator(NAIVE, data, ATT)
    clustered = run_estimator(CLUSTERED, data, ATT)
    assert clustered.estimate == pytest.approx(naive.estimate)
    assert clustered.std_error > 3 * naive.std_error
    assert "CR1 clustered on state" in clustered.inference_method
    assert clustered.details["cluster_diagnostics"]["n_clusters"] == 40  # type: ignore[index,call-overload]


def test_few_clusters_warn_and_too_few_refuse() -> None:
    assert check_clusters(np.arange(50)).status is DiagnosticStatus.PASS
    assert "few_clusters" in check_clusters(np.arange(12)).codes()
    assert check_clusters(np.arange(3)).is_blocking
    treated = np.array([True, False] + [False] * 48)
    assert "few_treated_clusters" in check_clusters(np.arange(50), treated).codes()


def test_estimator_refuses_too_few_clusters(rng: np.random.Generator) -> None:
    with pytest.raises(ClusterInferenceError, match="below the minimum"):
        run_estimator(CLUSTERED, state_panel(rng, n_states=4, per_state=20), ATT)


def test_policy_is_configurable() -> None:
    policy = ClusterPolicy(warn_below=5, refuse_below=2)
    assert check_clusters(np.arange(6), policy=policy).status is DiagnosticStatus.PASS


def test_units_must_be_nested_in_clusters(rng: np.random.Generator) -> None:
    data = state_panel(rng, n_states=10, per_state=5)
    data.loc[data.index[1], "state"] = 99  # same unit appears in two states
    with pytest.raises(ValueError, match="nested"):
        run_estimator(CLUSTERED, data, ATT)


def test_event_study_clusters_on_declared_level(rng: np.random.Generator) -> None:
    data = state_panel(rng, n_states=30, per_state=10)
    result = twfe_event_study(data, PanelSpec(cluster="state"))
    assert result.metrics["n_clusters"] == 30
    assert "clustered by state" in str(result.metrics["inference"])


@pytest.mark.simulation
def test_naive_inference_undercovers_clustered_does_not(rng: np.random.Generator) -> None:
    sims = 150
    naive_cover = clustered_cover = 0
    for _ in range(sims):
        data = state_panel(rng, n_states=40, per_state=20)
        n = run_estimator(NAIVE, data, ATT)
        c = run_estimator(CLUSTERED, data, ATT)
        naive_cover += n.ci_lower <= 1.0 <= n.ci_upper
        clustered_cover += c.ci_lower <= 1.0 <= c.ci_upper
    assert naive_cover / sims < 0.6
    assert 0.89 <= clustered_cover / sims <= 0.99
