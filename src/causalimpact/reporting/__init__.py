"""Assumption-aware report generation per REPORTING_STANDARD."""

from causalimpact.reporting.report import (
    REQUIRED_SECTIONS,
    Report,
    Section,
    build_report,
    render_markdown,
)

__all__ = ["REQUIRED_SECTIONS", "Report", "Section", "build_report", "render_markdown"]
