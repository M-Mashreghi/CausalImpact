"""Synthetic data-generating processes with known effects and benchmarks."""

from causalimpact.simulation.dgp import (
    ObservationalConfig,
    PanelConfig,
    RCTConfig,
    SimulatedDataset,
    SimulationConfig,
    simulate,
)

__all__ = [
    "ObservationalConfig",
    "PanelConfig",
    "RCTConfig",
    "SimulatedDataset",
    "SimulationConfig",
    "simulate",
]
