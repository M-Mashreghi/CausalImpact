"""Task 8.3: deployment artefacts and the production app factory.

The container smoke test itself (``scripts/smoke_container.sh``) needs Docker and runs in
CI; these tests cover everything that can be checked without it.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from causalimpact.api.server import build_app
from causalimpact.config import Settings
from causalimpact.domain import DESIGN_LIFECYCLE_FIELDS
from tests.integration.scenarios import rct
from tests.integration.test_api import EXPERIMENT, TREATMENT, promote

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]


def test_production_app_is_healthy_and_persists_runs(
    rng: np.random.Generator, tmp_path: Path
) -> None:
    settings = Settings(env="test", db_url=f"sqlite:///{tmp_path / 'var' / 'ci.db'}")
    client = TestClient(build_app(settings))
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json()["components"] == {"registry": "ok"}

    s = rct(rng, n=600)
    for estimand in s.service.estimands:
        client.post("/estimands", json=estimand.model_dump(mode="json"))
    draft = s.design.model_dump(mode="json", exclude=set(DESIGN_LIFECYCLE_FIELDS))
    design_id = client.post("/designs", json=draft).json()["design_id"]
    promote(client, design_id)
    run = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "difference_in_means", "treatment": TREATMENT},
            "data": {"records": s.data.to_dict(orient="records")},
            "seed": 1,
            "diagnostics": {"experiment": EXPERIMENT},
        },
    ).json()

    restarted = TestClient(build_app(settings))  # simulates a container restart
    assert (
        restarted.get(f"/runs/{run['run']['run_id']}").json()["run_fingerprint"]
        == (run["run_fingerprint"])
    )
    assert restarted.get(f"/designs/{design_id}").json()["status"] == "analysis_ready"


def test_demo_data_script_writes_synthetic_datasets(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/make_demo_data.py"), "--out", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    for name in ("checkout_experiment", "programme_observational", "policy_panel"):
        assert (tmp_path / name / "data.csv").exists()
        assert (tmp_path / name / "truth.json").exists()


def test_dockerfile_is_locked_non_root_and_health_checked() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert "pip install --require-hashes -r requirements.lock" in dockerfile
    assert "USER app" in dockerfile
    assert "HEALTHCHECK" in dockerfile and "/health" in dockerfile
    assert "make_demo_data.py" in dockerfile  # demo data only, generated at build
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "service_healthy" in compose and "_stcore/health" in compose
    ignored = (ROOT / ".dockerignore").read_text().split()
    assert {"data", ".env", "*.db"} <= set(ignored)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_requirements_lock_matches_uv_lock(tmp_path: Path) -> None:
    out = tmp_path / "requirements.lock"
    subprocess.run(
        [
            "uv", "export", "--frozen", "--no-dev", "--extra", "dashboard",
            "--no-emit-project", "-o", str(out), "-q",
        ],
        cwd=ROOT,
        check=True,
    )  # fmt: skip

    def body(path: Path) -> list[str]:
        return [ln for ln in path.read_text().splitlines() if not ln.startswith("#")]

    assert body(out) == body(ROOT / "requirements.lock")
