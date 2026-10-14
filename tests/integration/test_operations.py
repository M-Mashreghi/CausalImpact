"""Task 8.5: operational procedures documented and the invalidation tool works."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from causalimpact.services.registry import AnalysisRegistry
from causalimpact.services.run_spec import execute
from tests.integration.scenarios import rct
from tests.integration.test_registry import RCT_SPEC

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_invalidation_script_keeps_history(rng: np.random.Generator, tmp_path: Path) -> None:
    s = rct(rng, n=400)
    db = tmp_path / "ci.db"
    registry = AnalysisRegistry(db)
    results = [execute(s.service, s.design, RCT_SPEC, s.data) for _ in range(2)]
    for r in results:
        registry.save_run(r, RCT_SPEC)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/invalidate_run.py"), "--db", str(db), "--all",
         "--run", results[0].run_fingerprint, "--reason", "SE bug fixed in abc123"],
        check=True,
        capture_output=True,
    )  # fmt: skip
    records = registry.runs()
    assert len(records) == 2 and all(r.invalidated for r in records)
    assert registry.result(results[0].run.run_id) == results[0]


@pytest.mark.parametrize(
    ("doc", "phrases"),
    [
        ("docs/RUNBOOK.md", ["Backup and recovery", "Invalidating results", "/ready", "error_id"]),
        ("docs/SECURITY.md", ["pip-audit", "scrubbing", "synthetic", "unprivileged"]),
        (
            "docs/RELEASE_CHECKLIST.md",
            ["Research gates", "reproduced = True", "Model risk", "not supported"],
        ),
    ],
)
def test_operational_docs_cover_required_topics(doc: str, phrases: list[str]) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    for phrase in phrases:
        assert phrase in text, f"{doc} lacks {phrase!r}"


def test_demo_release_checklist_is_complete() -> None:
    template = (ROOT / "docs/RELEASE_CHECKLIST.md").read_text(encoding="utf-8")
    release = (ROOT / "docs/releases/v0.1.0-demo.md").read_text(encoding="utf-8")
    assert "- [ ]" not in release
    n_items = template.count("- [ ]")
    assert release.count("- [x]") == n_items, "every checklist item needs evidence"
