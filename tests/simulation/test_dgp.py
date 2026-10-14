"""Task 7.1: synthetic DGPs are seed-reproducible and carry their true estimands."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from causalimpact.panel.contract import PanelSpec, validate_panel
from causalimpact.simulation.dgp import (
    ObservationalConfig,
    PanelConfig,
    RCTConfig,
    simulate,
)

pytestmark = pytest.mark.simulation

CONFIGS = [RCTConfig(), ObservationalConfig(), PanelConfig(n_units=60)]


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.kind)
def test_seed_reproducibility(config: object) -> None:
    a, b = simulate(config, seed=42), simulate(config, seed=42)  # type: ignore[arg-type]
    assert a.dataset_version == b.dataset_version
    assert a.truth == b.truth
    assert simulate(config, seed=43).dataset_version != a.dataset_version  # type: ignore[arg-type]


@pytest.mark.parametrize("config", CONFIGS, ids=lambda c: c.kind)
def test_truth_is_persisted(config: object, tmp_path: Path) -> None:
    ds = simulate(config, seed=1)  # type: ignore[arg-type]
    out = ds.save(tmp_path / ds.config.kind)
    manifest = json.loads((out / "truth.json").read_text())
    assert manifest["truth"] == ds.truth
    assert manifest["seed"] == 1 and manifest["dataset_version"] == ds.dataset_version
    assert manifest["config"]["kind"] == ds.config.kind


def test_rct_truth_and_failure_switches() -> None:
    ds = simulate(RCTConfig(n=20_000, effect=0.5, heterogeneity=0.0), seed=0)
    assert ds.truth["ITT"] == pytest.approx(0.5)
    srm = simulate(RCTConfig(n=20_000, realized_treated_share=0.45), seed=0).data
    assert (srm["arm"] == "treatment").mean() == pytest.approx(0.45, abs=0.01)
    att = simulate(RCTConfig(n=20_000, attrition_treated=0.2), seed=0).data
    missing = att.groupby("arm")["y"].apply(lambda s: s.isna().mean())
    assert missing["treatment"] == pytest.approx(0.2, abs=0.02) and missing["control"] == 0
    clustered = simulate(RCTConfig(n=1000, cluster_size=10), seed=0).data
    assert (clustered.groupby("cluster_id")["arm"].nunique() == 1).all()


def test_observational_truths_differ_under_heterogeneity() -> None:
    truth = simulate(ObservationalConfig(n=50_000, heterogeneity=1.0), seed=0).truth
    assert truth["ATT"] > truth["ATE"] > truth["ATC"]
    assert truth["ATE"] == pytest.approx(truth["population_ATE"], abs=0.02)


def test_observational_naive_contrast_is_confounded() -> None:
    data = simulate(ObservationalConfig(n=20_000), seed=0).data
    naive = data.groupby("treated")["y"].mean()
    assert naive[1] - naive[0] > 4.0  # truth is about 2


def test_panel_dgp_is_a_valid_staggered_panel() -> None:
    ds = simulate(PanelConfig(n_units=200, cohorts=(4, 6), n_periods=8), seed=0)
    result, timing = validate_panel(ds.data, PanelSpec())
    assert not result.is_blocking
    assert timing is not None and timing.is_staggered and timing.balanced
    assert ds.truth["dynamic_0"] == 1.0
    assert 1.0 <= ds.truth["ATT_post_average"] <= 3.0


def test_panel_pre_trend_switch() -> None:
    data = simulate(PanelConfig(n_units=400, pre_trend_slope=0.5), seed=0).data
    ever = data["treatment_start"].notna()
    pre = data[(data["period"] <= 3)]
    gap = (
        pre[ever[pre.index]].groupby("period")["outcome"].mean()
        - pre[~ever[pre.index]].groupby("period")["outcome"].mean()
    )
    assert np.polyfit(gap.index, gap.to_numpy(), 1)[0] == pytest.approx(0.5, abs=0.2)
