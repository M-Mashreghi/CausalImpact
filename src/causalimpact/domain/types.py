"""Shared constrained types for domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator


def _non_blank(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError("must not be blank")
    return stripped


NonBlankStr = Annotated[str, AfterValidator(_non_blank)]


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_aware)]


def utc_now() -> datetime:
    return datetime.now(UTC)
