"""Panel / policy evaluation: DiD, event studies, synthetic control."""

from causalimpact.panel.contract import PanelSpec, PanelTiming, annotate_timing, validate_panel
from causalimpact.panel.did import TwoPeriodDiD
from causalimpact.panel.event_study import relative_time, twfe_event_study
from causalimpact.panel.multi_period import ComparisonGroup, SingleCohortDiD
from causalimpact.panel.pre_trends import check_pre_trends
from causalimpact.panel.synthetic_control import SyntheticControl, SyntheticFit

__all__ = [
    "ComparisonGroup",
    "PanelSpec",
    "PanelTiming",
    "SingleCohortDiD",
    "SyntheticControl",
    "SyntheticFit",
    "TwoPeriodDiD",
    "annotate_timing",
    "check_pre_trends",
    "relative_time",
    "twfe_event_study",
    "validate_panel",
]
