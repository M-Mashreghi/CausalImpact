"""Immutable, prefixed identifiers for domain objects.

Ids are opaque strings of the form ``<prefix>_<32 lowercase hex chars>``. The prefix makes
it impossible to pass, e.g., a run id where a design id is expected without a validation
error.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from pydantic import AfterValidator

_HEX32 = r"[0-9a-f]{32}"


def _id_validator(prefix: str) -> AfterValidator:
    pattern = re.compile(rf"^{prefix}_{_HEX32}$")

    def check(value: str) -> str:
        if not pattern.fullmatch(value):
            raise ValueError(f"expected id of the form '{prefix}_<32 hex>', got {value!r}")
        return value

    return AfterValidator(check)


DESIGN_PREFIX = "design"
RUN_PREFIX = "run"

DesignId = Annotated[str, _id_validator(DESIGN_PREFIX)]
RunId = Annotated[str, _id_validator(RUN_PREFIX)]


def new_design_id() -> str:
    return f"{DESIGN_PREFIX}_{uuid.uuid4().hex}"


def new_run_id() -> str:
    return f"{RUN_PREFIX}_{uuid.uuid4().hex}"
