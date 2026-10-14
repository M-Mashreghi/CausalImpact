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
from causalimpact.simulation.failure_modes import (
    FailureModeReport,
    ScenarioResult,
    run_failure_mode_suite,
)
from causalimpact.simulation.stress import StressPoint, overlap_sweep

__all__ = [
    "BenchmarkCase",
    "BenchmarkResult",
    "CoverageGate",
    "CoverageSummary",
    "FailureModeReport",
    "ObservationalConfig",
    "PanelConfig",
    "RCTConfig",
    "ScenarioResult",
    "SimulatedDataset",
    "SimulationConfig",
    "StressPoint",
    "bias_within_tolerance",
    "check_coverage",
    "coverage_summary",
    "overlap_sweep",
    "run_benchmark",
    "run_failure_mode_suite",
    "simulate",
]
