"""Dashboard data adapters: diagnostic artifacts -> tidy, plot-ready frames (Task 6.4).

Every frame carries the ``run_id`` it came from so each plot is traceable to an
AnalysisRun. Adapters only reshape stored numbers; they never compute causal quantities.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from causalimpact.diagnostics.base import DiagnosticResult
from causalimpact.sensitivity.specification import SpecificationReport
from causalimpact.services.analysis import AnalysisResult


def _metrics(result: DiagnosticResult, expected: str) -> dict[str, Any]:
    if result.name != expected:
        raise ValueError(f"expected a '{expected}' diagnostic, got '{result.name}'")
    return dict(result.metrics)


def _with_run(frame: pd.DataFrame, run_id: str) -> pd.DataFrame:
    return frame.assign(run_id=run_id)


def diagnostic_summary_frame(result: AnalysisResult) -> pd.DataFrame:
    rows = [
        {
            "diagnostic": d.name,
            "status": d.status.value,
            "required": d.name in result.required_diagnostics,
            "codes": ", ".join(sorted(d.codes())),
        }
        for d in result.diagnostics
    ]
    frame = pd.DataFrame(rows, columns=["diagnostic", "status", "required", "codes"])
    return _with_run(frame, result.run.run_id)


def srm_frame(result: DiagnosticResult, run_id: str) -> pd.DataFrame:
    m = _metrics(result, "sample_ratio_mismatch")
    arms = list(m["observed"])
    frame = pd.DataFrame(
        {
            "arm": arms,
            "observed": [m["observed"][a] for a in arms],
            "expected": [m["expected"][a] for a in arms],
            "observed_share": [m["observed_allocation"][a] for a in arms],
            "configured_share": [m["configured_allocation"][a] for a in arms],
        }
    )
    return _with_run(frame, run_id)


def balance_frame(result: DiagnosticResult, run_id: str) -> pd.DataFrame:
    """Love-plot rows from ``covariate_balance`` or ``baseline_balance`` diagnostics."""
    m: dict[str, Any] = dict(result.metrics)
    if "love_plot" in m:
        frame = pd.DataFrame(m["love_plot"])
    elif "table" in m:
        frame = pd.DataFrame(m["table"]).rename(columns={"comparison": "adjustment"})
    else:
        raise ValueError(f"'{result.name}' has no balance table")
    frame = frame[["adjustment", "covariate", "level", "smd"]].copy()
    frame["abs_smd"] = frame["smd"].abs()
    frame["threshold"] = m.get("smd_threshold", m.get("threshold"))
    return _with_run(frame, run_id)


def overlap_frame(result: DiagnosticResult, run_id: str) -> pd.DataFrame:
    m = _metrics(result, "overlap")
    edges = m["histogram_bin_edges"]
    rows = [
        {"arm": arm, "bin_left": edges[i], "bin_right": edges[i + 1], "count": count}
        for arm in ("treated", "control")
        for i, count in enumerate(m[arm]["histogram"])
    ]
    return _with_run(pd.DataFrame(rows), run_id)


def weights_frame(estimate_details: dict[str, Any], run_id: str) -> pd.DataFrame:
    weights = estimate_details.get("weights")
    if not isinstance(weights, dict):
        raise ValueError("estimate details carry no weight diagnostics")
    rows = [
        {
            "arm": arm,
            "effective_sample_size": weights[arm]["effective_sample_size"],
            "max_weight": weights[arm]["max"],
            "max_unit_share": weights[arm]["max_unit_share"],
            "n_extreme": weights[arm]["n_extreme"],
        }
        for arm in ("treated", "control")
    ]
    return _with_run(pd.DataFrame(rows), run_id)


def event_study_frame(result: DiagnosticResult, run_id: str) -> pd.DataFrame:
    m = _metrics(result, "event_study_twfe")
    frame = pd.DataFrame(m["coefficients"])[
        ["relative_time", "coef", "ci_lower", "ci_upper", "reference"]
    ]
    frame["label"] = m["label"]
    return _with_run(frame.sort_values("relative_time").reset_index(drop=True), run_id)


def specification_frame(report: SpecificationReport, run_id: str) -> pd.DataFrame:
    rows = [
        {
            "label": o.label,
            "primary": o.is_primary,
            "status": o.status.value,
            "estimate": None if o.estimate is None else o.estimate.estimate,
            "ci_lower": None if o.estimate is None else o.estimate.ci_lower,
            "ci_upper": None if o.estimate is None else o.estimate.ci_upper,
            "error": o.error,
        }
        for o in report.outcomes
    ]
    frame = pd.DataFrame(rows).assign(grid_fingerprint=report.grid_fingerprint)
    return _with_run(frame, run_id)
