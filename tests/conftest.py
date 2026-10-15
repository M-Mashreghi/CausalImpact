"""Shared pytest fixtures.

Determinism: tests never use global numpy RNG state. Any test needing randomness takes
the ``rng`` fixture, which is seeded from a fixed project-wide test seed.
"""

from __future__ import annotations

import os

# Must precede the numpy import. With parallel workers (pytest -n) each process would
# otherwise start one BLAS thread per core, which exhausts memory on Windows and crashes
# workers and subprocesses. Subprocesses inherit the setting through the environment.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

TEST_SEED = 20240101


@pytest.fixture
def rng() -> np.random.Generator:
    """A freshly seeded generator, identical for every test that requests it."""
    return np.random.default_rng(TEST_SEED)
