"""Task 8.1: design -> estimate -> diagnostics -> report for every supported family."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from causalimpact.domain import TreatmentSpec
from causalimpact.reporting import REQUIRED_SECTIONS, build_report, render_markdown
from causalimpact.services import InterpretationStatus
from causalimpact.services.estimator_factory import (
    AIPWConfig,
    DifferenceInMeansConfig,
    SingleCohortDiDConfig,
)
from causalimpact.services.registry import export_bundle, rerun_bundle
from causalimpact.services.run_spec import DiagnosticsConfig, RunSpec, execute
from tests.integration.scenarios import Scenario, X, observational, panel_policy, rct

pytestmark = pytest.mark.e2e

EXPERIMENT = {
    "experiment_id": "checkout",
    "arms": [{"name": "control", "allocation": 0.5}, {"name": "treatment", "allocation": 0.5}],
    "control_arm": "control",
    "randomization_unit": "user_id",
    "analysis_unit": "user_id",
    "primary_metric": "revenue",
}
FAMILIES = {
    "randomized": (
        rct,
        RunSpec(
            estimator=DifferenceInMeansConfig(
                treatment=TreatmentSpec(
                    name="arm", control_value="control", treated_value="treatment"
                )
            ),
            diagnostics=DiagnosticsConfig.model_validate({"experiment": EXPERIMENT}),
            seed=1,
        ),
        {"sample_ratio_mismatch", "attrition"},
        0.3,
    ),
    "observational": (
        observational,
        RunSpec(
            estimator=AIPWConfig(treatment=TreatmentSpec(name="treated"), covariates=(X,)),
            seed=2,
        ),
        {"overlap"},
        2.0,
    ),
    "panel": (
        panel_policy,
        RunSpec(estimator=SingleCohortDiDConfig(), seed=3),
        {"pre_trends"},
        2.25,  # post periods 5-8 have effects (1, 2, 3, 3); the DGP caps at the last value
    ),
}


@pytest.mark.parametrize("family", list(FAMILIES))
def test_family_end_to_end(family: str, rng: np.random.Generator, tmp_path: Path) -> None:
    make, spec, diagnostics, truth = FAMILIES[family]
    s: Scenario = make(rng)
    result = execute(s.service, s.design, spec, s.data)

    assert {d.name for d in result.diagnostics} == diagnostics
    assert result.interpretation is InterpretationStatus.SUPPORTED, result.reasons
    assert result.estimate is not None
    assert abs(result.estimate.estimate - truth) < 4 * result.estimate.std_error

    report = build_report(result)
    assert tuple(s.title for s in report.sections) == REQUIRED_SECTIONS
    assert result.run.run_id in render_markdown(report)

    check = rerun_bundle(export_bundle(result, spec, s.data, s.service, tmp_path / family))
    assert check.reproduced


@pytest.mark.parametrize(
    ("family", "make_kwargs"),
    [
        ("randomized", {"srm": True}),
        ("observational", {"strength": 6.0}),
        ("panel", {"pre_trend_slope": 0.4}),
    ],
)
def test_family_blocked_path(
    family: str, make_kwargs: dict[str, object], rng: np.random.Generator
) -> None:
    make, spec, _, _ = FAMILIES[family]
    s: Scenario = make(rng, **make_kwargs)
    result = execute(s.service, s.design, spec, s.data)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED
    assert result.estimate is None
    md = render_markdown(build_report(result))
    assert "Causal interpretation not supported" in md and "**blocking**" in md
