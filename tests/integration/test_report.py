"""Task 6.6: the report fixture contains every required section."""

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pytest

from causalimpact.reporting.report import REQUIRED_SECTIONS, build_report, render_markdown
from causalimpact.sensitivity.specification import (
    SpecificationGrid,
    SpecificationVariant,
    run_specifications,
)
from causalimpact.sensitivity.trimming import PolicyKind, TrimmingPolicy, run_trimming_sensitivity
from causalimpact.services import InterpretationStatus
from tests.integration.scenarios import X, observational, rct

pytestmark = pytest.mark.integration


def test_supported_rct_report_has_all_sections(rng: np.random.Generator) -> None:
    s = rct(rng)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    report = build_report(result)
    assert tuple(sec.title for sec in report.sections) == REQUIRED_SECTIONS
    md = render_markdown(report)
    for title in REQUIRED_SECTIONS:
        assert f"## {title}" in md
    assert "Causal estimate supported under stated assumptions" in md
    assert "95% interval" in md
    assert result.run.run_id in md and result.run.dataset_version in md
    assert "Neyman (1923)" in md
    assert "Alternative specifications: not run" in md  # never silently omitted
    assert "no_interference" in report.section("Limitations").lines[-2]


def test_blocked_report_shows_failure_and_no_estimate(rng: np.random.Generator) -> None:
    s = rct(rng, srm=True)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    md = render_markdown(build_report(result))
    assert InterpretationStatus.NOT_SUPPORTED.value in md
    assert InterpretationStatus.SUPPORTED.value not in md
    assert "No estimate is reported" in md
    assert "srm_detected" in md and "**blocking**" in md
    assert "Fabijan" in md


def test_robustness_artifacts_are_rendered(rng: np.random.Generator) -> None:
    s = observational(rng, n=1500)
    result = s.service.run(s.design, s.estimator, s.data, diagnostics=s.diagnostics, seed=1)
    declared, run_at = datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC)
    grid = SpecificationGrid(
        (SpecificationVariant("aipw", s.estimator),), primary="aipw", declared_at=declared
    )
    specs = run_specifications(grid, s.data, result.estimand, run_at=run_at)
    from causalimpact.domain import TreatmentSpec
    from causalimpact.observational.weighting import WeightingEstimator, WeightScheme

    ipw = WeightingEstimator(
        TreatmentSpec(name="treated"), (X,), WeightScheme.IPW, seed=1, n_bootstrap=50
    )
    trimming = run_trimming_sensitivity(
        s.data,
        TreatmentSpec(name="treated"),
        (X,),
        result.estimand,
        ipw,
        (
            TrimmingPolicy(kind=PolicyKind.NONE),
            TrimmingPolicy(kind=PolicyKind.PROPENSITY_TRIM, alpha=0.05),
        ),
        declared_at=declared,
        run_at=run_at,
    )
    md = render_markdown(build_report(result, specifications=specs, trimming=trimming))
    assert "1 declared, 1 succeeded" in md
    assert "ate_y__trim_0.05 (population restricted)" in md
    assert "Robins, Rotnitzky & Zhao" in md
    assert "conditional_exchangeability [untestable" in md
