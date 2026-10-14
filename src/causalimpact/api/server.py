"""Production app factory: settings, logging and the persistent registry.

uvicorn --factory causalimpact.api.server:build_app
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from causalimpact.api.app import ApiState, create_app
from causalimpact.config.observability import configure_logging
from causalimpact.config.settings import Settings
from causalimpact.services.registry import AnalysisRegistry


def build_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    registry: AnalysisRegistry | None = None
    if settings.sqlite_path is not None:
        Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        registry = AnalysisRegistry(settings.sqlite_path)
    state = ApiState(settings=settings, registry=registry)
    if registry is not None:
        state.estimands, state.dags = registry.load_registries()
    return create_app(state)
