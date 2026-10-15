"""Task 4.9: synthetic control through the declarative run path, fail-closed on bad fit."""

from __future__ import annotations

import numpy as np
import pytest

from causalimpact.services import InterpretationStatus, RunSpec, execute
from causalimpact.services.estimator_factory import SyntheticControlConfig
from tests.integration.scenarios import panel_policy
from tests.unit.panel.test_synthetic_control import panel

pytestmark = pytest.mark.integration
SPEC = RunSpec(estimator=SyntheticControlConfig(), seed=1)


def test_synthetic_control_end_to_end(rng: np.random.Generator) -> None:
    s = panel_policy(rng)
    result = execute(s.service, s.design, SPEC, panel(rng, own_sd=0.0, noise=0.1))
    assert [d.name for d in result.diagnostics] == ["synthetic_control_fit", "placebo_in_space"]
    assert result.estimate is not None and result.estimate.estimator == "synthetic_control"
    assert result.interpretation is InterpretationStatus.SUPPORTED


def test_poor_fit_withholds_the_estimate(rng: np.random.Generator) -> None:
    s = panel_policy(rng)
    data = panel(rng)
    data.loc[data.unit_id == "treated", "outcome"] += 100.0  # outside every donor's range
    result = execute(s.service, s.design, SPEC, data)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED
    assert result.estimate is None


def test_placebos_downgrade_a_null_effect_to_suggestive(rng: np.random.Generator) -> None:
    s = panel_policy(rng)
    spec = RunSpec(estimator=SyntheticControlConfig(placebo_period=9), seed=1)
    result = execute(s.service, s.design, spec, panel(rng, effect=0.0, noise=0.3))
    names = [d.name for d in result.diagnostics]
    assert names == ["synthetic_control_fit", "placebo_in_space", "placebo_in_time"]
    assert "effect_not_extreme_among_placebos" in result.diagnostics[1].codes()
    assert result.estimate is not None  # placebos never withhold the estimate...
    assert result.interpretation is InterpretationStatus.SUGGESTIVE  # ...but downgrade it
