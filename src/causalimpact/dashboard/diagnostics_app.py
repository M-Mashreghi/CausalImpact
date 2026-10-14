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


def main() -> None:
    st.title("CausalImpact diagnostics")
    path = st.text_input("Path to an analysis result (JSON)", key="result_path")
    if not path:
        st.info("Enter the path of a saved analysis result.")
        return
    try:
        result = AnalysisResult.model_validate_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        st.error(f"Could not load the analysis result: {type(exc).__name__}")
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
