"""Task 6.7: fixture bundles rerun deterministically; runs persist append-only."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from causalimpact.domain import TreatmentSpec
from causalimpact.services.estimator_factory import AIPWConfig, DifferenceInMeansConfig
from causalimpact.services.registry import (
    AnalysisRegistry,
    BundleIntegrityError,
    export_bundle,
    rerun_bundle,
)
from causalimpact.services.run_spec import DiagnosticsConfig, RunSpec, execute
from tests.integration.scenarios import X, observational, rct

pytestmark = pytest.mark.integration

RCT_SPEC = RunSpec(
    estimator=DifferenceInMeansConfig(
        treatment=TreatmentSpec(name="arm", control_value="control", treated_value="treatment")
    ),
    seed=11,
)
OBS_SPEC = RunSpec(
    estimator=AIPWConfig(treatment=TreatmentSpec(name="treated"), covariates=(X,)),
    diagnostics=DiagnosticsConfig(),
    seed=5,
)


def test_rct_bundle_reruns_deterministically(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng)
    result = execute(s.service, s.design, RCT_SPEC, s.data)
    bundle = export_bundle(result, RCT_SPEC, s.data, s.service, tmp_path / "bundle")
    manifest = json.loads((bundle / "manifest.json").read_text())
    assert set(manifest["artifacts"]) >= {"data.csv", "design.json", "result.json", "report.md"}
    check = rerun_bundle(bundle)
    assert check.reproduced
    assert check.rerun.run.run_id != check.original_run_id  # a new execution...
    assert check.rerun.run_fingerprint == manifest["run_fingerprint"]  # ...of the same spec


def test_observational_bundle_with_dag_reruns(rng: np.random.Generator, tmp_path: Path) -> None:
    s = observational(rng, n=1000)
    result = execute(s.service, s.design, OBS_SPEC, s.data)
    bundle = export_bundle(result, OBS_SPEC, s.data, s.service, tmp_path / "obs")
    assert (bundle / "dag.json").exists() and (bundle / "adjustment_set.json").exists()
    check = rerun_bundle(bundle)
    assert check.reproduced
    assert [d.name for d in check.rerun.diagnostics] == ["overlap"]


def test_tampered_bundle_is_rejected(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng)
    result = execute(s.service, s.design, RCT_SPEC, s.data)
    bundle = export_bundle(result, RCT_SPEC, s.data, s.service, tmp_path / "b")
    csv = (bundle / "data.csv").read_text()
    (bundle / "data.csv").write_text(csv.replace("treatment", "control", 1))
    with pytest.raises(BundleIntegrityError, match=r"data.csv"):
        rerun_bundle(bundle)


def test_registry_persists_and_invalidates_without_overwrite(
    rng: np.random.Generator, tmp_path: Path
) -> None:
    s = rct(rng)
    registry = AnalysisRegistry(tmp_path / "ci.db")
    registry.save_design(s.design)
    for estimand in s.service.estimands:
        registry.save_estimand(estimand)
    result = execute(s.service, s.design, RCT_SPEC, s.data)
    registry.save_run(result, RCT_SPEC)

    reopened = AnalysisRegistry(tmp_path / "ci.db")
    assert reopened.result(result.run.run_id) == result
    assert reopened.spec(result.run.run_id) == RCT_SPEC
    assert reopened.design(s.design.design_id) == s.design
    estimands, _ = reopened.load_registries()
    assert "itt_revenue" in estimands

    reopened.invalidate(result.run.run_id, "bug in SE formula")
    record = reopened.runs(s.design.design_id)[0]
    assert record.invalidated and record.invalidation_reason == "bug in SE formula"
    assert reopened.result(result.run.run_id) == result  # history preserved


def test_registry_refuses_redefined_estimand(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng)
    registry = AnalysisRegistry(tmp_path / "ci.db")
    estimand = next(iter(s.service.estimands))
    registry.save_estimand(estimand)
    with pytest.raises(ValueError, match="stored differently"):
        registry.save_estimand(estimand.model_copy(update={"outcome": "other"}))


def test_bundle_dtypes_round_trip(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng, n=200)
    data = s.data.assign(segment=np.where(s.data.index % 2 == 0, "a", "b"))
    result = execute(s.service, s.design, RCT_SPEC, data)
    bundle = export_bundle(result, RCT_SPEC, data, s.service, tmp_path / "d")
    assert rerun_bundle(bundle).reproduced  # dtypes restored, dataset hash matches
