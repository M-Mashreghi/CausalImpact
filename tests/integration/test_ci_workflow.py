"""Task 8.4: workflow syntax and quality gates are validated."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def workflow() -> dict:  # type: ignore[type-arg]
    return yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def _runs(job: dict) -> str:  # type: ignore[type-arg]
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_workflow_parses_with_required_jobs(workflow: dict) -> None:  # type: ignore[type-arg]
    assert set(workflow["jobs"]) == {
        "quality",
        "tests",
        "research-gates",
        "security",
        "container",
        "ci-gate",
    }
    triggers = workflow[True] if True in workflow else workflow["on"]  # YAML 1.1 "on"
    assert "pull_request" in triggers and "push" in triggers
    assert workflow["permissions"] == {"contents": "read"}


def test_quality_gates_are_present(workflow: dict) -> None:  # type: ignore[type-arg]
    jobs = workflow["jobs"]
    assert "ruff check" in _runs(jobs["quality"]) and "mypy" in _runs(jobs["quality"])
    assert "ruff format --check" in _runs(jobs["quality"])
    assert 'pytest -m "not simulation"' in _runs(jobs["tests"])
    research = _runs(jobs["research-gates"])
    assert "pytest -m simulation" in research and "research_gates.py" in research
    security = _runs(jobs["security"])
    assert "pip-audit" in security and "uv lock --check" in security
    assert "smoke_container.sh" in _runs(jobs["container"])


def test_gate_job_blocks_on_any_failure(workflow: dict) -> None:  # type: ignore[type-arg]
    gate = workflow["jobs"]["ci-gate"]
    assert set(gate["needs"]) == {"quality", "tests", "research-gates", "security", "container"}
    assert gate["if"] == "always()"
    assert "failure" in _runs(gate) and "skipped" in _runs(gate)


def test_actions_are_version_pinned(workflow: dict) -> None:  # type: ignore[type-arg]
    uses = [s["uses"] for j in workflow["jobs"].values() for s in j["steps"] if "uses" in s]
    assert uses and all("@" in u for u in uses)


def test_ci_does_not_need_external_apis(workflow: dict) -> None:  # type: ignore[type-arg]
    text = (ROOT / ".github/workflows/ci.yml").read_text()
    assert "secrets." not in text  # mandatory CI must not depend on external credentials


def test_compose_file_parses() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    assert set(compose["services"]) == {"api", "dashboard"}


@pytest.mark.simulation
def test_research_gates_script_passes(tmp_path: Path) -> None:
    out = tmp_path / "gates.json"
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts/research_gates.py"), "--out", str(out),
         "--replicates", "80"],
        capture_output=True,
        text=True,
    )  # fmt: skip
    assert done.returncode == 0, done.stdout[-2000:]
    assert out.exists()
