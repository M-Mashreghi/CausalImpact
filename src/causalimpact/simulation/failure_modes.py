"""DiD / experiment failure-mode simulation suite (Task 7.6).

Each scenario simulates a known failure (or its clean control) several times and checks
whether the corresponding diagnostic labels it. The report is written as a JSON artifact
for CI regression gates: every failure mode must be detected at a high rate and every
clean control must rarely raise a false alarm.

Repeated peeking is included as a *demonstration*: monitoring a fixed-horizon test at
every interim look inflates the false-positive rate. Automatic detection of peeking
misuse is the sequential-monitoring guardrail (Task 2.12, Advanced) and is not claimed
here; the scenario is reported with ``detector="not implemented (Task 2.12)"``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from scipy import stats

from causalimpact.diagnostics.base import DiagnosticResult
from causalimpact.domain.fingerprint import derive_seed
from causalimpact.experiments.attrition import check_attrition
from causalimpact.experiments.spec import Arm, ExperimentSpec
from causalimpact.experiments.srm import check_srm_from_assignments
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.event_study import twfe_event_study
from causalimpact.panel.pre_trends import check_pre_trends
from causalimpact.simulation.dgp import PanelConfig, RCTConfig, simulate

EXPERIMENT = ExperimentSpec(
    experiment_id="simulated",
    arms=(Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
    control_arm="control",
    randomization_unit="unit_id",
    analysis_unit="unit_id",
    primary_metric="y",
)


class ScenarioResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    failure_injected: bool
    detector: str
    n_replicates: int
    detection_rate: float | None
    codes_seen: tuple[str, ...]
    note: str


class FailureModeReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    scenarios: tuple[ScenarioResult, ...]

    def scenario(self, name: str) -> ScenarioResult:
        for s in self.scenarios:
            if s.name == name:
                return s
        raise KeyError(name)

    def write(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        return out


Detector = Callable[[pd.DataFrame], DiagnosticResult]


def _srm(df: pd.DataFrame) -> DiagnosticResult:
    return check_srm_from_assignments(EXPERIMENT, df)


def _attrition(df: pd.DataFrame) -> DiagnosticResult:
    return check_attrition(EXPERIMENT, df, df, "y")


def _pre_trends(df: pd.DataFrame) -> DiagnosticResult:
    return check_pre_trends(twfe_event_study(df, PanelSpec()))


def _event_study(df: pd.DataFrame) -> DiagnosticResult:
    return twfe_event_study(df, PanelSpec())


def _run(
    name: str,
    injected: bool,
    detector_name: str,
    detector: Detector,
    flagged_codes: set[str],
    make: Callable[[int], pd.DataFrame],
    seed: int,
    n_replicates: int,
    note: str,
) -> ScenarioResult:
    hits, codes = 0, set[str]()
    for rep in range(n_replicates):
        result = detector(make(derive_seed(seed, f"{name}:{rep}")))
        seen = result.codes()
        codes |= seen
        hits += bool(seen & flagged_codes)
    return ScenarioResult(
        name=name,
        failure_injected=injected,
        detector=detector_name,
        n_replicates=n_replicates,
        detection_rate=hits / n_replicates,
        codes_seen=tuple(sorted(codes)),
        note=note,
    )


def _peeking(seed: int, n_replicates: int, looks: int = 10, alpha: float = 0.05) -> ScenarioResult:
    """Null RCT monitored at every look with a fixed-horizon t-test."""
    false_positives = 0
    for rep in range(n_replicates):
        rng = np.random.default_rng(derive_seed(seed, f"peeking:{rep}"))
        n = 2000
        arm = rng.integers(0, 2, n)
        y = rng.normal(size=n)
        for k in range(1, looks + 1):
            m = n * k // looks
            p = stats.ttest_ind(y[:m][arm[:m] == 1], y[:m][arm[:m] == 0], equal_var=False).pvalue
            if p < alpha:
                false_positives += 1
                break
    rate = false_positives / n_replicates
    return ScenarioResult(
        name="repeated_peeking",
        failure_injected=True,
        detector="not implemented (Task 2.12)",
        n_replicates=n_replicates,
        detection_rate=None,
        codes_seen=(),
        note=f"null effect, {looks} fixed-horizon looks: false-positive rate {rate:.3f} vs "
        f"nominal {alpha}; demonstrates why repeated peeking is prohibited",
    )


def run_failure_mode_suite(*, seed: int = 0, n_replicates: int = 10) -> FailureModeReport:
    def rct(**kw: object) -> Callable[[int], pd.DataFrame]:
        return lambda s: simulate(RCTConfig(n=10_000, **kw), s).data

    def panel(**kw: object) -> Callable[[int], pd.DataFrame]:
        return lambda s: simulate(PanelConfig(n_units=300, **kw), s).data

    srm_codes, attr_codes = {"srm_detected"}, {"differential_attrition"}
    trend_codes, stag_codes = {"pre_trend_detected"}, {"twfe_event_study_staggered"}
    scenarios = (
        _run("srm", True, "check_srm", _srm, srm_codes, rct(realized_treated_share=0.46),
             seed, n_replicates, "realised treated share 0.46 vs configured 0.5"),
        _run("srm_control", False, "check_srm", _srm, srm_codes, rct(),
             seed, n_replicates, "correct allocation"),
        _run("differential_attrition", True, "check_attrition", _attrition, attr_codes,
             rct(attrition_treated=0.1), seed, n_replicates, "10% outcomes lost in treatment only"),
        _run("attrition_control", False, "check_attrition", _attrition, attr_codes,
             rct(attrition_treated=0.05, attrition_control=0.05), seed, n_replicates,
             "equal 5% attrition in both arms"),
        _run("pre_trend", True, "check_pre_trends", _pre_trends, trend_codes,
             panel(pre_trend_slope=0.3), seed, n_replicates, "treated drift 0.3 per period"),
        _run("pre_trend_control", False, "check_pre_trends", _pre_trends, trend_codes,
             panel(), seed, n_replicates, "parallel paths"),
        _run("staggered_heterogeneity", True, "twfe_event_study", _event_study, stag_codes,
             panel(cohorts=(3, 6), cohort_effect_scale=(1.0, 3.0)), seed, n_replicates,
             "two cohorts with different effect sizes"),
        _run("single_cohort_control", False, "twfe_event_study", _event_study, stag_codes,
             panel(), seed, n_replicates, "one adoption cohort"),
        _peeking(seed, n_replicates=max(n_replicates * 20, 200)),
    )  # fmt: skip
    return FailureModeReport(seed=seed, scenarios=scenarios)
