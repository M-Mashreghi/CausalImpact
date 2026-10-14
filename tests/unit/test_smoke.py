"""Task 1.1 smoke tests: the package installs, imports and has a deterministic test env."""

from __future__ import annotations

import importlib
import sys
from importlib.metadata import version

import numpy as np
import pytest

import causalimpact

SUBPACKAGES = [
    "config",
    "domain",
    "ingestion",
    "validation",
    "design",
    "dags",
    "experiments",
    "observational",
    "panel",
    "estimators",
    "diagnostics",
    "sensitivity",
    "heterogeneity",
    "simulation",
    "reporting",
    "services",
    "api",
    "dashboard",
]


def test_package_version_matches_metadata() -> None:
    assert causalimpact.__version__ == version("causalimpact")


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports(name: str) -> None:
    module = importlib.import_module(f"causalimpact.{name}")
    assert module.__doc__, f"causalimpact.{name} must document its responsibility"


def test_supported_python_baseline() -> None:
    assert sys.version_info >= (3, 12)


def test_rng_fixture_is_deterministic(rng: np.random.Generator) -> None:
    expected = np.random.default_rng(20240101).normal(size=5)
    np.testing.assert_array_equal(rng.normal(size=5), expected)
