"""Shared pytest fixtures.

Determinism: tests never use global numpy RNG state. Any test needing randomness takes
the ``rng`` fixture, which is seeded from a fixed project-wide test seed.
"""

from __future__ import annotations

import numpy as np
import pytest

TEST_SEED = 20240101


@pytest.fixture
def rng() -> np.random.Generator:
    """A freshly seeded generator, identical for every test that requests it."""
    return np.random.default_rng(TEST_SEED)
