"""Streamlit diagnostics dashboard (Task 6.4).

Run with:  streamlit run src/causalimpact/dashboard/diagnostics_app.py

Loads a saved ``AnalysisResult`` JSON and renders its diagnostics via the adapters.
Every chart is captioned with the AnalysisRun id it belongs to.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from causalimpact.dashboard.adapters import (
    balance_frame,
    diagnostic_summary_frame,
    event_study_frame,
    overlap_frame,
    srm_frame,
    weights_frame,
)
from causalimpact.services.analysis import AnalysisResult


def resolve_result_path(raw: str) -> tuple[Path | None, str]:
    """Accept a result.json path or a bundle folder; tolerate pasted quotes."""
    path = Path(raw.strip().strip('"').strip("'"))
    if path.is_dir():
        path = path / "result.json"
    if not path.is_file():
        return None, f"No analysis result found at {path}."
    return path, ""


def main() -> None:
    st.title("CausalImpact diagnostics")
    raw = st.text_input(
        "Path to an analysis result: a result.json file or a bundle folder", key="result_path"
    )
    if not raw:
        st.info("Enter the path of a saved analysis result or reproducibility bundle folder.")
        return
    path, problem = resolve_result_path(raw)
    if path is None:
        st.error(problem)
        return
    try:
        result = AnalysisResult.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        st.error(f"Could not read {path}: {exc.strerror or type(exc).__name__}")
        return
    except ValidationError:
        st.error(f"{path} is not a CausalImpact analysis result.")
        return

    run_id = result.run.run_id
    st.subheader(result.interpretation.value)
    st.caption(f"AnalysisRun {run_id} · fingerprint {result.run_fingerprint}")
    for reason in result.reasons:
        st.write(f"- {reason}")
    st.dataframe(diagnostic_summary_frame(result))

    for diag in result.diagnostics:
        st.subheader(diag.name)
        st.caption(f"AnalysisRun {run_id}")
        if diag.name == "sample_ratio_mismatch" and "observed" in diag.metrics:
            st.bar_chart(srm_frame(diag, run_id), x="arm", y=["observed", "expected"])
        elif diag.name in {"baseline_balance", "covariate_balance"}:
            frame = balance_frame(diag, run_id)
            st.dataframe(frame)
        elif diag.name == "overlap":
            frame = overlap_frame(diag, run_id)
            st.bar_chart(frame, x="bin_left", y="count", color="arm")
        elif diag.name == "event_study_twfe":
            st.line_chart(event_study_frame(diag, run_id), x="relative_time", y="coef")
        for finding in diag.findings:
            st.warning(f"[{finding.severity}] {finding.code}: {finding.message}")

    if result.estimate is not None and "weights" in result.estimate.details:
        st.subheader("weights")
        st.caption(f"AnalysisRun {run_id}")
        st.dataframe(weights_frame(dict(result.estimate.details), run_id))


main()
