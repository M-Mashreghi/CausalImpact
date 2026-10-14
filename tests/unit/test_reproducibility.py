"""Task 1.7: dataset versions, seeds and run fingerprints are reproducible."""

from __future__ import annotations

import subprocess
import sys
from typing import Any

import numpy as np
import pandas as pd
import pytest

from causalimpact.domain import (
    AnalysisRun,
    DesignStatus,
    RunStatus,
    StudyDesign,
    content_hash,
    derive_seed,
)
from causalimpact.ingestion import dataset_version
from tests.unit.domain.test_study_design import advance_to, make_design


@pytest.fixture
def frame(rng: np.random.Generator) -> pd.DataFrame:
    n = 50
    return pd.DataFrame(
        {
            "unit_id": [f"u{i}" for i in range(n)],
            "treated": rng.integers(0, 2, size=n),
            "y": rng.normal(size=n),
            "segment": pd.Categorical(rng.choice(["a", "b"], size=n)),
        }
    )


class TestDatasetVersion:
    def test_same_content_same_hash(self, frame: pd.DataFrame) -> None:
        assert dataset_version(frame) == dataset_version(frame.copy(deep=True))

    def test_column_order_and_index_are_ignored(self, frame: pd.DataFrame) -> None:
        shuffled = frame[["y", "segment", "unit_id", "treated"]].set_axis(range(100, 150), axis=0)
        assert dataset_version(shuffled).content_hash == dataset_version(frame).content_hash

    def test_row_order_matters(self, frame: pd.DataFrame) -> None:
        reversed_rows = frame.iloc[::-1]
        assert dataset_version(reversed_rows).content_hash != dataset_version(frame).content_hash

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda d: d.assign(y=d.y.where(d.index != 7, d.y + 1e-12)),
            lambda d: d.assign(treated=d.treated.astype("int32")),
            lambda d: d.rename(columns={"y": "outcome"}),
            lambda d: d.iloc[:-1],
            lambda d: d.assign(y=d.y.where(d.index != 3)),
            lambda d: d.assign(extra=1),
        ],
    )
    def test_any_change_changes_hash(self, frame: pd.DataFrame, mutate: Any) -> None:
        assert dataset_version(mutate(frame)).content_hash != dataset_version(frame).content_hash

    def test_metadata(self, frame: pd.DataFrame) -> None:
        version = dataset_version(frame)
        assert version.n_rows == 50
        assert version.content_hash.startswith("sha256:")
        assert [c.name for c in version.columns] == sorted(frame.columns)

    def test_duplicate_columns_rejected(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            dataset_version(pd.DataFrame([[1, 2]], columns=["a", "a"]))

    def test_hash_is_stable_across_processes(self) -> None:
        code = (
            "import pandas as pd; from causalimpact.ingestion import dataset_version;"
            "print(dataset_version(pd.DataFrame({'a':[1,2,3],'b':['x','y',None],"
            "'c':[0.5,float('nan'),2.0]})).content_hash)"
        )
        outputs = {
            subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, check=True
            ).stdout.strip()
            for _ in range(2)
        }
        local = dataset_version(
            pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", None], "c": [0.5, float("nan"), 2.0]})
        ).content_hash
        assert outputs == {local}


class TestSeeds:
    def test_derived_seed_is_deterministic_and_purpose_specific(self) -> None:
        assert derive_seed(42, "bootstrap") == derive_seed(42, "bootstrap")
        assert derive_seed(42, "bootstrap") != derive_seed(42, "crossfit_folds")
        assert derive_seed(42, "bootstrap") != derive_seed(43, "bootstrap")
        assert 0 <= derive_seed(42, "x") < 2**63

    def test_seed_reproduces_random_stream(self) -> None:
        a = np.random.default_rng(derive_seed(7, "folds")).permutation(100)
        b = np.random.default_rng(derive_seed(7, "folds")).permutation(100)
        np.testing.assert_array_equal(a, b)

    def test_negative_root_seed_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            derive_seed(-1, "x")

    def test_content_hash_rejects_nan(self) -> None:
        with pytest.raises(ValueError):
            content_hash({"alpha": float("nan")})

    def test_content_hash_ignores_key_order(self) -> None:
        assert content_hash({"a": 1, "b": [1, 2]}) == content_hash({"b": [1, 2], "a": 1})


SPEC: dict[str, Any] = {
    "estimator": "aipw",
    "dataset_version": "sha256:" + "0" * 64,
    "seed": 11,
    "nuisance_learners": {"propensity": {"model": "logit", "C": 1.0}},
    "config": {"trim": [0.01, 0.99]},
    "code_version": "0.1.0",
}


@pytest.fixture
def design() -> StudyDesign:
    return advance_to(make_design(dag_version="dag_v1"), DesignStatus.ANALYSIS_READY)


class TestRunFingerprint:
    def test_same_inputs_same_fingerprint_and_seeds(self, design: StudyDesign) -> None:
        a = AnalysisRun.for_design(design, **SPEC)
        b = AnalysisRun.for_design(design, **SPEC)
        assert a.run_id != b.run_id  # distinct executions...
        assert a.fingerprint == b.fingerprint  # ...of one specification
        assert a.derived_seed("bootstrap") == b.derived_seed("bootstrap")

    def test_fingerprint_survives_lifecycle_and_serialization(self, design: StudyDesign) -> None:
        run = AnalysisRun.for_design(design, **SPEC)
        done = run.transition(RunStatus.RUNNING).transition(RunStatus.COMPLETED)
        invalid = done.transition(RunStatus.INVALIDATED, reason="bug")
        restored = AnalysisRun.model_validate_json(invalid.model_dump_json())
        assert {done.fingerprint, invalid.fingerprint, restored.fingerprint} == {run.fingerprint}

    @pytest.mark.parametrize(
        "change",
        [
            {"estimator": "ipw"},
            {"dataset_version": "sha256:" + "1" * 64},
            {"seed": 12},
            {"confidence_level": 0.9},
            {"nuisance_learners": {"propensity": {"model": "logit", "C": 0.5}}},
            {"config": {"trim": [0.05, 0.95]}},
            {"code_version": "0.2.0"},
        ],
    )
    def test_changed_config_changes_fingerprint(
        self, design: StudyDesign, change: dict[str, Any]
    ) -> None:
        base = AnalysisRun.for_design(design, **SPEC)
        changed = AnalysisRun.for_design(design, **{**SPEC, **change})
        assert changed.fingerprint != base.fingerprint

    def test_design_content_change_changes_fingerprint(self, design: StudyDesign) -> None:
        base = AnalysisRun.for_design(design, **SPEC)
        reopened = design.transition(DesignStatus.DRAFT, reason="fix outcome window")
        revised = advance_to(
            reopened.revise(reason="fix", outcome="converted_14d"), DesignStatus.ANALYSIS_READY
        )
        rerun = AnalysisRun.for_design(revised, **SPEC)
        assert rerun.design_content_hash != base.design_content_hash
        assert rerun.fingerprint != base.fingerprint

    def test_design_content_hash_ignores_lifecycle(self) -> None:
        draft = make_design()
        validated = draft.transition(DesignStatus.VALIDATED, reason="ok")
        twin = make_design()  # new id and timestamp, same content
        assert draft.content_hash == validated.content_hash == twin.content_hash
