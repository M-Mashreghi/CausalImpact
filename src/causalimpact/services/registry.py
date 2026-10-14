"""Analysis registry, re-run and reproducibility bundles (Task 6.7).

``AnalysisRegistry`` persists designs, estimands, DAGs, adjustment sets and analysis
results in SQLite. Results are append-only: invalidation is recorded as an event and the
original result is never overwritten (RUNBOOK.md, "Result invalidation").

A reproducibility bundle is a directory containing everything needed to re-run one
analysis: ``manifest.json`` (run id, fingerprint, dataset version, run spec, artifact
hashes), the design / estimand / DAG / adjustment-set JSON, the dataset as CSV with its
recorded dtypes, the result JSON and the rendered report. ``rerun_bundle`` verifies every
file hash and the dataset content hash, re-runs the analysis and checks that the
specification fingerprint and the estimate are reproduced exactly.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel, ConfigDict

from causalimpact.dags import AdjustmentSet, CausalDAG, DagRegistry
from causalimpact.domain.estimands import Estimand, EstimandRegistry
from causalimpact.domain.study_design import StudyDesign
from causalimpact.domain.types import utc_now
from causalimpact.ingestion.dataset_version import dataset_version
from causalimpact.services.analysis import AnalysisResult, AnalysisService
from causalimpact.services.run_spec import RunSpec, execute

SCHEMA = """
CREATE TABLE IF NOT EXISTS designs (design_id TEXT, version INTEGER, body TEXT,
    PRIMARY KEY (design_id, version));
CREATE TABLE IF NOT EXISTS estimands (estimand_id TEXT PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS dags (version TEXT PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS adjustment_sets (version TEXT PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, design_id TEXT, fingerprint TEXT,
    interpretation TEXT, spec TEXT, result TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS run_events (run_id TEXT, event TEXT, reason TEXT, at TEXT);
"""


class RunRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str
    design_id: str
    fingerprint: str
    interpretation: str
    invalidated: bool
    invalidation_reason: str | None


class AnalysisRegistry:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as db:
            db.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    # -- design artefacts ---------------------------------------------------------

    def save_design(self, design: StudyDesign) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO designs VALUES (?, ?, ?)",
                (design.design_id, design.version, design.model_dump_json()),
            )

    def save_estimand(self, estimand: Estimand) -> None:
        with self._connect() as db:
            existing = db.execute(
                "SELECT body FROM estimands WHERE estimand_id = ?", (estimand.estimand_id,)
            ).fetchone()
            if existing and Estimand.model_validate_json(existing[0]) != estimand:
                raise ValueError(f"estimand {estimand.estimand_id!r} already stored differently")
            db.execute(
                "INSERT OR IGNORE INTO estimands VALUES (?, ?)",
                (estimand.estimand_id, estimand.model_dump_json()),
            )

    def save_dag(self, dag: CausalDAG) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO dags VALUES (?, ?)", (dag.version, dag.model_dump_json())
            )

    def save_adjustment_set(self, adjustment: AdjustmentSet) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO adjustment_sets VALUES (?, ?)",
                (adjustment.version, adjustment.model_dump_json()),
            )

    def load_registries(self) -> tuple[EstimandRegistry, DagRegistry]:
        estimands, dags = EstimandRegistry(), DagRegistry()
        with self._connect() as db:
            for (body,) in db.execute("SELECT body FROM estimands"):
                estimands.register(Estimand.model_validate_json(body))
            for (body,) in db.execute("SELECT body FROM dags"):
                dags.register_dag(CausalDAG.model_validate_json(body))
            for (body,) in db.execute("SELECT body FROM adjustment_sets"):
                dags.register_adjustment_set(AdjustmentSet.model_validate_json(body))
        return estimands, dags

    def design(self, design_id: str, version: int | None = None) -> StudyDesign:
        query = "SELECT body FROM designs WHERE design_id = ?"
        args: tuple[object, ...] = (design_id,)
        if version is not None:
            query += " AND version = ?"
            args += (version,)
        with self._connect() as db:
            row = db.execute(query + " ORDER BY version DESC LIMIT 1", args).fetchone()
        if row is None:
            raise KeyError(design_id)
        return StudyDesign.model_validate_json(row[0])

    # -- runs -----------------------------------------------------------------------

    def save_run(self, result: AnalysisResult, spec: RunSpec) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    result.run.run_id,
                    result.run.design_id,
                    result.run_fingerprint,
                    result.interpretation.value,
                    spec.model_dump_json(),
                    result.model_dump_json(),
                    result.run.created_at.isoformat(),
                ),
            )

    def result(self, run_id: str) -> AnalysisResult:
        with self._connect() as db:
            row = db.execute("SELECT result FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return AnalysisResult.model_validate_json(row[0])

    def spec(self, run_id: str) -> RunSpec:
        with self._connect() as db:
            row = db.execute("SELECT spec FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunSpec.model_validate_json(row[0])

    def invalidate(self, run_id: str, reason: str, at: datetime | None = None) -> None:
        if not reason.strip():
            raise ValueError("invalidation requires a reason")
        self.result(run_id)  # must exist
        with self._connect() as db:
            db.execute(
                "INSERT INTO run_events VALUES (?, 'invalidated', ?, ?)",
                (run_id, reason, (at or utc_now()).isoformat()),
            )

    def runs(self, design_id: str | None = None) -> list[RunRecord]:
        query = "SELECT run_id, design_id, fingerprint, interpretation FROM runs"
        args: tuple[object, ...] = ()
        if design_id is not None:
            query += " WHERE design_id = ?"
            args = (design_id,)
        with self._connect() as db:
            rows = db.execute(query + " ORDER BY created_at", args).fetchall()
            events = dict(
                db.execute("SELECT run_id, reason FROM run_events WHERE event = 'invalidated'")
            )
        return [
            RunRecord(
                run_id=r[0],
                design_id=r[1],
                fingerprint=r[2],
                interpretation=r[3],
                invalidated=r[0] in events,
                invalidation_reason=events.get(r[0]),
            )
            for r in rows
        ]


# -- reproducibility bundles ------------------------------------------------------------


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def export_bundle(
    result: AnalysisResult,
    spec: RunSpec,
    data: pd.DataFrame,
    service: AnalysisService,
    directory: str | Path,
) -> Path:
    # Imported here: reporting depends on services.analysis, and services' package
    # initialiser imports this module, so a top-level import would be circular.
    from causalimpact.reporting.report import build_report, render_markdown

    out = Path(directory)
    out.mkdir(parents=True, exist_ok=False)
    design = result.design
    files: dict[str, str] = {
        "design.json": design.model_dump_json(indent=2),
        "estimand.json": result.estimand.model_dump_json(indent=2),
        "run_spec.json": spec.model_dump_json(indent=2),
        "result.json": result.model_dump_json(indent=2),
        "report.md": render_markdown(build_report(result)),
        "dtypes.json": json.dumps({str(c): str(t) for c, t in data.dtypes.items()}, indent=2),
    }
    if design.dag_version is not None:
        files["dag.json"] = service.dags.dag(design.dag_version).model_dump_json(indent=2)
    if design.adjustment_set_version is not None:
        files["adjustment_set.json"] = service.dags.adjustment_set(
            design.adjustment_set_version
        ).model_dump_json(indent=2)
    for name, body in files.items():
        (out / name).write_text(body, encoding="utf-8", newline="\n")
    data.to_csv(out / "data.csv", index=False, lineterminator="\n")
    names = sorted([*files, "data.csv"])
    manifest = {
        "run_id": result.run.run_id,
        "run_fingerprint": result.run_fingerprint,
        "dataset_version": result.run.dataset_version,
        "code_version": result.run.code_version,
        "artifacts": {name: _sha256(out / name) for name in names},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


class BundleIntegrityError(RuntimeError):
    """A bundle file or the dataset does not match its recorded hash."""


@dataclass(frozen=True)
class RerunCheck:
    original_run_id: str
    rerun: AnalysisResult
    fingerprint_matches: bool
    estimate_matches: bool
    interpretation_matches: bool

    @property
    def reproduced(self) -> bool:
        return self.fingerprint_matches and self.estimate_matches and self.interpretation_matches


def load_bundle_data(directory: Path) -> pd.DataFrame:
    dtypes = json.loads((directory / "dtypes.json").read_text(encoding="utf-8"))
    frame = pd.read_csv(directory / "data.csv", float_precision="round_trip")
    return frame.astype(dtypes)


def rerun_bundle(directory: str | Path) -> RerunCheck:
    root = Path(directory)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["artifacts"].items():
        if _sha256(root / name) != digest:
            raise BundleIntegrityError(f"{name} does not match its recorded hash")
    data = load_bundle_data(root)
    if dataset_version(data).content_hash != manifest["dataset_version"]:
        raise BundleIntegrityError("re-loaded dataset does not match the recorded version")

    estimands, dags = EstimandRegistry(), DagRegistry()
    estimands.register(Estimand.model_validate_json((root / "estimand.json").read_text("utf-8")))
    if (root / "dag.json").exists():
        dags.register_dag(CausalDAG.model_validate_json((root / "dag.json").read_text("utf-8")))
    if (root / "adjustment_set.json").exists():
        dags.register_adjustment_set(
            AdjustmentSet.model_validate_json((root / "adjustment_set.json").read_text("utf-8"))
        )
    design = StudyDesign.model_validate_json((root / "design.json").read_text("utf-8"))
    spec = RunSpec.model_validate_json((root / "run_spec.json").read_text("utf-8"))
    original = AnalysisResult.model_validate_json((root / "result.json").read_text("utf-8"))
    rerun = execute(AnalysisService(estimands, dags), design, spec, data)
    return RerunCheck(
        original_run_id=manifest["run_id"],
        rerun=rerun,
        fingerprint_matches=rerun.run_fingerprint == manifest["run_fingerprint"],
        estimate_matches=rerun.estimate == original.estimate,
        interpretation_matches=rerun.interpretation == original.interpretation,
    )
