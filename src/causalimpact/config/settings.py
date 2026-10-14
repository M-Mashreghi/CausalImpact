"""Runtime settings from the environment (``.env.example`` documents the keys)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

Environment = Literal["development", "test", "production"]


@dataclass(frozen=True)
class Settings:
    env: Environment = "development"
    db_url: str = "sqlite:///./data/causalimpact.db"
    log_level: str = "INFO"

    @property
    def sqlite_path(self) -> str | None:
        prefix = "sqlite:///"
        return self.db_url[len(prefix) :] if self.db_url.startswith(prefix) else None

    @classmethod
    def from_env(cls) -> Settings:
        env = os.environ.get("CAUSALIMPACT_ENV", "development")
        if env not in ("development", "test", "production"):
            raise ValueError("CAUSALIMPACT_ENV must be development, test or production")
        return cls(
            env=env,  # type: ignore[arg-type]
            db_url=os.environ.get("CAUSALIMPACT_DB_URL", cls.db_url),
            log_level=os.environ.get("CAUSALIMPACT_LOG_LEVEL", cls.log_level).upper(),
        )
