"""Task 8.2: health/readiness endpoints and log scrubbing."""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from causalimpact.api import ApiState, create_app
from causalimpact.config import REDACTED, Settings, configure_logging, log_event, scrub, scrub_text
from causalimpact.config.observability import JsonFormatter, ScrubFilter
from causalimpact.services.registry import AnalysisRegistry
from tests.integration.scenarios import rct

pytestmark = pytest.mark.integration


@pytest.fixture
def captured() -> io.StringIO:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ScrubFilter())
    root = logging.getLogger("causalimpact")
    old = (root.handlers, root.level, root.propagate)
    root.handlers, root.level, root.propagate = [handler], logging.INFO, False
    yield stream
    root.handlers, root.level, root.propagate = old


def lines(stream: io.StringIO) -> list[dict[str, object]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


@pytest.mark.parametrize(
    ("raw", "secret"),
    [
        ("login failed password=hunter2 for user", "hunter2"),
        ("api_key: sk-live-123abc", "sk-live-123abc"),
        ("Authorization: Bearer eyJhbGciOi.payload.sig", "eyJhbGciOi.payload.sig"),
        ("connect postgresql://admin:s3cr3t@db.internal/causal", "s3cr3t"),
        ("token=abc&next=1", "abc"),
    ],
)
def test_scrub_text(raw: str, secret: str) -> None:
    cleaned = scrub_text(raw)
    assert secret not in cleaned and REDACTED in cleaned


def test_scrub_nested_fields() -> None:
    cleaned = scrub({"user": "ann", "auth": {"password": "x", "API_KEY": "y"}, "db_url": "z"})
    assert cleaned == {
        "user": "ann",
        "auth": {"password": REDACTED, "API_KEY": REDACTED},
        "db_url": REDACTED,
    }


def test_structured_log_is_scrubbed_json(captured: io.StringIO) -> None:
    logger = logging.getLogger("causalimpact.test")
    log_event(logger, "connecting with secret=topsecret", run_id="run_1", token="abc123")
    (record,) = lines(captured)
    assert record["run_id"] == "run_1" and record["token"] == REDACTED
    assert "topsecret" not in json.dumps(record)
    assert {"ts", "level", "logger", "event"} <= record.keys()


def test_analysis_runs_emit_lifecycle_events_without_data(
    captured: io.StringIO, rng: np.random.Generator
) -> None:
    s = rct(rng, n=500)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    events = {r["event"]: r for r in lines(captured)}
    started, finished = events["analysis_run_started"], events["analysis_run_finished"]
    assert started["run_id"] == finished["run_id"] == result.run.run_id
    assert finished["interpretation"] == result.interpretation.value
    assert "revenue" not in json.dumps(started).replace('"estimand_id": "itt_revenue"', "")


def test_health_and_ready(tmp_path: Path) -> None:
    client = TestClient(create_app(ApiState()))
    assert client.get("/health").json() == {"status": "ok"}
    body = client.get("/ready").json()
    assert body["status"] == "ready" and body["components"] == {"registry": "not_configured"}

    registry = AnalysisRegistry(tmp_path / "ci.db")
    settings = Settings(env="test", db_url="sqlite:///secret-path/ci.db")
    ok = TestClient(create_app(ApiState(settings=settings, registry=registry))).get("/ready")
    assert ok.status_code == 200 and ok.json()["components"] == {"registry": "ok"}
    assert "secret-path" not in ok.text


def test_ready_reports_unavailable_registry(tmp_path: Path) -> None:
    registry = AnalysisRegistry(tmp_path / "ci.db")
    registry.path = str(tmp_path / "missing_dir" / "ci.db")
    response = TestClient(create_app(ApiState(registry=registry))).get("/ready")
    assert response.status_code == 503
    assert response.json()["components"] == {"registry": "unavailable"}


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAUSALIMPACT_ENV", "production")
    monkeypatch.setenv("CAUSALIMPACT_DB_URL", "sqlite:///./x.db")
    settings = Settings.from_env()
    assert settings.env == "production" and settings.sqlite_path == "./x.db"
    monkeypatch.setenv("CAUSALIMPACT_ENV", "staging")
    with pytest.raises(ValueError, match="CAUSALIMPACT_ENV"):
        Settings.from_env()


def test_configure_logging_installs_scrubbing_handler() -> None:
    configure_logging("WARNING")
    root = logging.getLogger("causalimpact")
    assert root.level == logging.WARNING
    assert any(isinstance(f, ScrubFilter) for f in root.handlers[0].filters)
