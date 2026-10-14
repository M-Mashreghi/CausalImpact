"""Synthetic data-generating processes with known effects and benchmarks."""

from causalimpact.simulation.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    bias_within_tolerance,
    run_benchmark,
)
from causalimpact.simulation.coverage import (
    CoverageGate,
    CoverageSummary,
    check_coverage,
    coverage_summary,
)
from causalimpact.simulation.dgp import (
    ObservationalConfig,
    PanelConfig,
    RCTConfig,
    SimulatedDataset,
    SimulationConfig,
    simulate,
)

__all__ = [
    "BenchmarkCase",
    "BenchmarkResult",
    "CoverageGate",
    "CoverageSummary",
    "ObservationalConfig",
    "PanelConfig",
    "RCTConfig",
    "SimulatedDataset",
    "SimulationConfig",
    "bias_within_tolerance",
    "check_coverage",
    "coverage_summary",
    "run_benchmark",
    "simulate",
]
