"""Panel / policy evaluation: DiD, event studies, synthetic control."""

from causalimpact.panel.contract import PanelSpec, PanelTiming, annotate_timing, validate_panel
from causalimpact.panel.did import TwoPeriodDiD
from causalimpact.panel.multi_period import ComparisonGroup, SingleCohortDiD

__all__ = [
    "ComparisonGroup",
    "PanelSpec",
    "PanelTiming",
    "SingleCohortDiD",
    "TwoPeriodDiD",
    "annotate_timing",
    "validate_panel",
]
