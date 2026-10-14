"""Panel / policy evaluation: DiD, event studies, synthetic control."""

from causalimpact.panel.contract import PanelSpec, PanelTiming, annotate_timing, validate_panel

__all__ = ["PanelSpec", "PanelTiming", "annotate_timing", "validate_panel"]
