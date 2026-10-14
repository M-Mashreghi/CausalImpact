"""Synthetic data-generating processes with known effects and benchmarks."""

from causalimpact.simulation.benchmark import (
    BenchmarkCase,
    BenchmarkResult,
    bias_within_tolerance,
    run_benchmark,
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
    "ObservationalConfig",
    "PanelConfig",
    "RCTConfig",
    "SimulatedDataset",
    "SimulationConfig",
    "bias_within_tolerance",
    "run_benchmark",
    "simulate",
]
