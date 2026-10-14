"""Task 6.2: API create / run / read contract tests."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient

from causalimpact.api import ApiState, create_app
from causalimpact.domain import DESIGN_LIFECYCLE_FIELDS
from tests.integration.scenarios import observational, rct

pytestmark = pytest.mark.integration

TREATMENT = {"name": "arm", "control_value": "control", "treated_value": "treatment"}
EXPERIMENT = {
    "experiment_id": "checkout",
    "arms": [{"name": "control", "allocation": 0.5}, {"name": "treatment", "allocation": 0.5}],
    "control_arm": "control",
    "randomization_unit": "user_id",
    "analysis_unit": "user_id",
    "primary_metric": "revenue",
}


def setup_rct(rng: np.random.Generator, **kw: Any) -> tuple[TestClient, str, list[dict[str, Any]]]:
    s = rct(rng, **kw)
    client = TestClient(create_app(ApiState()))
    for estimand in s.service.estimands:
        assert client.post("/estimands", json=estimand.model_dump(mode="json")).status_code == 201
    draft = s.design.model_dump(mode="json", exclude=set(DESIGN_LIFECYCLE_FIELDS))
    created = client.post("/designs", json=draft)
    assert created.status_code == 201, created.json()
    design_id = created.json()["design_id"]
    records = s.data.to_dict(orient="records")
    return client, design_id, records


def promote(client: TestClient, design_id: str) -> None:
    for status in ("validated", "analysis_ready"):
        r = client.post(f"/designs/{design_id}/transitions", json={"to": status, "reason": "ok"})
        assert r.status_code == 200, r.json()


def test_create_run_read_rct(rng: np.random.Generator) -> None:
    client, design_id, records = setup_rct(rng)
    assert client.get(f"/designs/{design_id}").json()["status"] == "draft"
    promote(client, design_id)
    response = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "difference_in_means", "treatment": TREATMENT},
            "data": {"records": records},
            "seed": 3,
            "diagnostics": {"experiment": EXPERIMENT},
        },
    )
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["interpretation"] == "Causal estimate supported under stated assumptions"
    assert body["estimate"]["estimand_type"] == "ITT"
    assert {d["name"] for d in body["diagnostics"]} == {"sample_ratio_mismatch", "attrition"}
    run_id = body["run"]["run_id"]
    assert client.get(f"/runs/{run_id}").json()["run_fingerprint"] == body["run_fingerprint"]
    listed = client.get(f"/designs/{design_id}/runs").json()
    assert [r["run_id"] for r in listed] == [run_id]


def test_srm_run_returns_not_supported(rng: np.random.Generator) -> None:
    client, design_id, records = setup_rct(rng, srm=True)
    promote(client, design_id)
    body = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "difference_in_means", "treatment": TREATMENT},
            "data": {"records": records},
            "seed": 3,
            "diagnostics": {"experiment": EXPERIMENT},
        },
    ).json()
    assert body["interpretation"] == "Causal interpretation not supported"
    assert body["estimate"] is None


def test_readiness_failure_lists_problems(rng: np.random.Generator) -> None:
    s = rct(rng)
    client = TestClient(create_app(ApiState()))  # estimand deliberately not registered
    draft = s.design.model_dump(mode="json", exclude=set(DESIGN_LIFECYCLE_FIELDS))
    design_id = client.post("/designs", json=draft).json()["design_id"]
    client.post(f"/designs/{design_id}/transitions", json={"to": "validated", "reason": "ok"})
    r = client.post(
        f"/designs/{design_id}/transitions", json={"to": "analysis_ready", "reason": "go"}
    )
    assert r.status_code == 409
    assert r.json()["error"] == "design_not_ready"
    assert any("estimand not registered" in p for p in r.json()["detail"])


def test_running_a_draft_design_is_refused(rng: np.random.Generator) -> None:
    client, design_id, records = setup_rct(rng)
    r = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "difference_in_means", "treatment": TREATMENT},
            "data": {"records": records},
            "seed": 1,
        },
    )
    assert r.status_code == 409


def test_observational_run_adds_overlap_diagnostic(rng: np.random.Generator) -> None:
    s = observational(rng, n=800)
    client = TestClient(create_app(ApiState(estimands=s.service.estimands, dags=s.service.dags)))
    draft = s.design.model_dump(mode="json", exclude=set(DESIGN_LIFECYCLE_FIELDS))
    design_id = client.post("/designs", json=draft).json()["design_id"]
    promote(client, design_id)
    x = {
        "name": "x",
        "dtype": "numeric",
        "measurement_time": "baseline",
        "pre_treatment": "true",
        "descendant_of_treatment": "false",
    }
    body = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "aipw", "treatment": {"name": "treated"}, "covariates": [x]},
            "data": {"records": s.data.to_dict(orient="records")},
            "seed": 2,
        },
    ).json()
    assert [d["name"] for d in body["diagnostics"]] == ["overlap"]
    assert body["estimate"]["estimand_type"] == "ATE"


def test_contract_errors(rng: np.random.Generator) -> None:
    client, design_id, records = setup_rct(rng)
    assert client.get("/designs/design_" + "0" * 32).status_code == 404
    assert client.get("/runs/run_missing").status_code == 404
    bad = client.post(
        f"/designs/{design_id}/runs",
        json={
            "estimator": {"kind": "magic", "treatment": TREATMENT},
            "data": {"records": records},
            "seed": 1,
        },
    )
    assert bad.status_code == 422
    extra = client.post("/designs", json={"title": "x", "favourite": 1})
    assert extra.status_code == 422


def test_unexpected_errors_do_not_leak_details() -> None:
    app = create_app(ApiState())

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("password=hunter2 at /srv/secret/path.py line 12")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")
    assert response.status_code == 500
    text = response.text
    assert "hunter2" not in text and "Traceback" not in text and "secret" not in text
    assert response.json()["error"] == "internal_error"
    assert len(response.json()["error_id"]) == 32


def test_health() -> None:
    assert TestClient(create_app()).get("/health").json() == {"status": "ok"}
