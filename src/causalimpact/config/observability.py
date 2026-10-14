"""Structured JSON logging with sensitive-data scrubbing (Task 8.2).

Every record is emitted as one JSON object with a timestamp, level, logger, event and
any structured fields. A scrubbing filter redacts, before formatting:

* values of sensitive keys (password, secret, token, api key, authorization, cookie,
  credentials, connection strings) in structured fields, at any nesting depth;
* ``key=value`` / ``key: value`` pairs and bearer tokens inside free-text messages;
* user:password credentials embedded in URLs.

Run logs carry identifiers and statuses, never data values.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"
SENSITIVE_KEY = re.compile(
    r"pass(word|wd)?|secret|token|api[_-]?key|authorization|cookie|credential|db_url|dsn",
    re.IGNORECASE,
)
_KV = re.compile(
    r"(?i)\b(pass(?:word|wd)?|secret|token|api[_-]?key|authorization|cookie)\b(\s*[=:]\s*)"
    r"([^\s,;&]+)"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+")
_URL_CREDS = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")


def scrub_text(text: str) -> str:
    text = _URL_CREDS.sub(rf"\1{REDACTED}@", text)
    text = _BEARER.sub(f"Bearer {REDACTED}", text)
    return _KV.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)


def scrub(value: Any, key: str | None = None) -> Any:
    if key is not None and SENSITIVE_KEY.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {k: scrub(v, str(k)) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [scrub(v) for v in value]
    if isinstance(value, str):
        return scrub_text(value)
    return value


class ScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = scrub_text(str(record.getMessage()))
        record.args = None
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            record.fields = scrub(fields)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = scrub_text(
                f"{record.exc_info[0].__name__ if record.exc_info[0] else 'Exception'}"
            )
        return json.dumps(payload, default=str, sort_keys=True)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(ScrubFilter())
    root = logging.getLogger("causalimpact")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: Any) -> None:
    """Emit a structured event; fields are scrubbed by the handler's filter."""
    logger.log(level, event, extra={"fields": fields})
