"""Panel / policy evaluation: DiD, event studies, synthetic control."""

from causalimpact.panel.contract import PanelSpec, PanelTiming, annotate_timing, validate_panel
from causalimpact.panel.did import TwoPeriodDiD

__all__ = ["PanelSpec", "PanelTiming", "TwoPeriodDiD", "annotate_timing", "validate_panel"]
