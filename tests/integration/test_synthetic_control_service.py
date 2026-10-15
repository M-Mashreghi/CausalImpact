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
    assert [d.name for d in result.diagnostics] == ["synthetic_control_fit"]
    assert result.estimate is not None and result.estimate.estimator == "synthetic_control"
    assert result.interpretation is InterpretationStatus.SUPPORTED


def test_poor_fit_withholds_the_estimate(rng: np.random.Generator) -> None:
    s = panel_policy(rng)
    data = panel(rng)
    data.loc[data.unit_id == "treated", "outcome"] += 100.0  # outside every donor's range
    result = execute(s.service, s.design, SPEC, data)
    assert result.interpretation is InterpretationStatus.NOT_SUPPORTED
    assert result.estimate is None
