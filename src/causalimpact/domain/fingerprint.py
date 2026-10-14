"""Canonical hashing and deterministic seed derivation.

All fingerprints are SHA-256 over canonical JSON (sorted keys, compact separators, NaN and
infinity rejected), so equal content always yields an equal fingerprint across processes
and platforms, and any change to the content changes it.
"""

from __future__ import annotations

import hashlib
import json

from pydantic import JsonValue

SEED_BITS = 63


def canonical_json(payload: JsonValue) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_hash(payload: JsonValue) -> str:
    """``sha256:<64 hex>`` fingerprint of a JSON-compatible payload."""
    return "sha256:" + hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def derive_seed(root_seed: int, *labels: str) -> int:
    """A child seed for a named purpose (e.g. ``"crossfit_folds"``, ``"bootstrap"``).

    Depends only on the root seed and the labels, never on call order, so adding a new
    random step does not shift the random stream of existing steps.
    """
    if root_seed < 0:
        raise ValueError("root_seed must be non-negative")
    digest = hashlib.sha256(canonical_json([root_seed, *labels]).encode()).digest()
    return int.from_bytes(digest[:8], "big") >> (64 - SEED_BITS)
