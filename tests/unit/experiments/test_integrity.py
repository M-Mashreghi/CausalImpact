"""Task 2.1: clean assignment fixtures pass; corrupted ones fail."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from causalimpact.diagnostics import DiagnosticResult, DiagnosticStatus
from causalimpact.experiments import Arm, ExperimentSpec, check_assignment_integrity

N = 200
T0 = pd.Timestamp("2026-03-01", tz="UTC")


def spec(**kw: Any) -> ExperimentSpec:
    fields: dict[str, Any] = {
        "experiment_id": "exp_checkout",
        "arms": (Arm(name="control", allocation=0.5), Arm(name="treatment", allocation=0.5)),
        "control_arm": "control",
        "randomization_unit": "user_id",
        "analysis_unit": "user_id",
        "assignment_time_column": "assigned_at",
        "exposure_time_column": "exposed_at",
        "primary_metric": "converted",
    }
    fields.update(kw)
    return ExperimentSpec(**fields)


@pytest.fixture
def logs(rng: np.random.Generator) -> dict[str, pd.DataFrame]:
    users = [f"u{i:03d}" for i in range(N)]
    arms = rng.permutation(np.repeat(["control", "treatment"], N // 2))
    assigned_at = T0 + pd.to_timedelta(rng.integers(0, 3600, N), unit="s")
    assignments = pd.DataFrame({"user_id": users, "arm": arms, "assigned_at": assigned_at})
    exposed = assignments.sample(frac=0.8, random_state=1)
    exposures = pd.DataFrame(
        {
            "user_id": exposed["user_id"],
            "arm": exposed["arm"],
            "exposed_at": exposed["assigned_at"] + pd.Timedelta(minutes=5),
        }
    )
    analysis = pd.DataFrame({"user_id": users, "arm": arms, "converted": rng.integers(0, 2, N)})
    return {"assignments": assignments, "exposures": exposures, "analysis": analysis}


def run(logs: dict[str, pd.DataFrame], s: ExperimentSpec | None = None) -> DiagnosticResult:
    return check_assignment_integrity(
        s or spec(), logs["assignments"], logs["analysis"], logs["exposures"]
    )


def test_clean_fixture_passes(logs: dict[str, pd.DataFrame]) -> None:
    result = run(logs)
    assert result.status is DiagnosticStatus.PASS, result.findings
    assert result.metrics["n_assigned_units"] == N
    assert result.metrics["assigned_by_arm"] == {"control": 100, "treatment": 100}


def test_clean_fixture_without_exposure_log_passes(logs: dict[str, pd.DataFrame]) -> None:
    result = check_assignment_integrity(spec(), logs["assignments"], logs["analysis"])
    assert result.status is DiagnosticStatus.PASS


def _corrupt_conflicting(logs: dict[str, pd.DataFrame]) -> None:
    row = logs["assignments"].iloc[[0]].copy()
    row["arm"] = "treatment" if row["arm"].iloc[0] == "control" else "control"
    logs["assignments"] = pd.concat([logs["assignments"], row], ignore_index=True)


def _corrupt_unknown_arm(logs: dict[str, pd.DataFrame]) -> None:
    logs["assignments"].loc[3, "arm"] = "treatment_v2"


def _corrupt_missing(logs: dict[str, pd.DataFrame]) -> None:
    logs["assignments"].loc[4, "arm"] = None


def _corrupt_cross_exposure(logs: dict[str, pd.DataFrame]) -> None:
    e = logs["exposures"]
    first = e.index[0]
    e.loc[first, "arm"] = "treatment" if e.loc[first, "arm"] == "control" else "control"


def _corrupt_unassigned_exposure(logs: dict[str, pd.DataFrame]) -> None:
    extra = pd.DataFrame({"user_id": ["ghost"], "arm": ["control"], "exposed_at": [T0]})
    logs["exposures"] = pd.concat([logs["exposures"], extra], ignore_index=True)


def _corrupt_early_exposure(logs: dict[str, pd.DataFrame]) -> None:
    e = logs["exposures"]
    e.loc[e.index[0], "exposed_at"] = T0 - pd.Timedelta(days=1)


def _corrupt_arm_mismatch(logs: dict[str, pd.DataFrame]) -> None:
    a = logs["analysis"]
    a.loc[0, "arm"] = "treatment" if a.loc[0, "arm"] == "control" else "control"


def _corrupt_duplicate_analysis(logs: dict[str, pd.DataFrame]) -> None:
    logs["analysis"] = pd.concat([logs["analysis"], logs["analysis"].iloc[[5]]])


def _corrupt_unassigned_analysis(logs: dict[str, pd.DataFrame]) -> None:
    extra = pd.DataFrame({"user_id": ["stranger"], "arm": ["control"], "converted": [1]})
    logs["analysis"] = pd.concat([logs["analysis"], extra], ignore_index=True)


@pytest.mark.parametrize(
    ("corrupt", "code"),
    [
        (_corrupt_conflicting, "conflicting_assignment"),
        (_corrupt_unknown_arm, "unknown_arm"),
        (_corrupt_missing, "missing_assignment_field"),
        (_corrupt_cross_exposure, "cross_arm_exposure"),
        (_corrupt_unassigned_exposure, "exposure_without_assignment"),
        (_corrupt_early_exposure, "exposure_before_assignment"),
        (_corrupt_arm_mismatch, "arm_mismatch"),
        (_corrupt_duplicate_analysis, "duplicate_analysis_unit"),
        (_corrupt_unassigned_analysis, "analysis_unit_not_assigned"),
    ],
)
def test_corrupted_fixture_blocks(logs: dict[str, pd.DataFrame], corrupt: Any, code: str) -> None:
    corrupt(logs)
    result = run(logs)
    assert result.is_blocking
    assert code in result.codes()
    assert result.finding(code).count >= 1


def test_conflicting_units_are_named(logs: dict[str, pd.DataFrame]) -> None:
    _corrupt_conflicting(logs)
    result = run(logs)
    assert result.finding("conflicting_assignment").examples == ("u000",)
    # The contaminated unit cannot be analysed as randomized either.
    assert "analysis_unit_not_assigned" in result.codes()


def test_duplicate_assignment_logging_is_a_warning(logs: dict[str, pd.DataFrame]) -> None:
    logs["assignments"] = pd.concat([logs["assignments"], logs["assignments"].iloc[[7]]])
    result = run(logs)
    assert result.status is DiagnosticStatus.WARNING
    assert result.codes() == {"duplicate_assignment"}


def test_missing_analysis_units_are_a_visible_warning(logs: dict[str, pd.DataFrame]) -> None:
    logs["analysis"] = logs["analysis"].iloc[10:]
    result = run(logs)
    assert result.status is DiagnosticStatus.WARNING
    assert result.finding("assigned_not_analyzed").count == 10


def test_missing_columns_block(logs: dict[str, pd.DataFrame]) -> None:
    logs["analysis"] = logs["analysis"].drop(columns="arm")
    result = run(logs)
    assert result.codes() == {"missing_column"}
    assert result.is_blocking


class TestClusterRandomization:
    @pytest.fixture
    def cluster_logs(self) -> dict[str, pd.DataFrame]:
        households = [f"h{i}" for i in range(20)]
        assignments = pd.DataFrame(
            {
                "household_id": households,
                "arm": ["control", "treatment"] * 10,
                "assigned_at": T0,
            }
        )
        rows = [
            {"user_id": f"{h}_m{m}", "household_id": h, "arm": arm}
            for h, arm in zip(households, assignments["arm"], strict=True)
            for m in range(3)
        ]
        return {"assignments": assignments, "analysis": pd.DataFrame(rows)}

    def _spec(self) -> ExperimentSpec:
        return spec(randomization_unit="household_id", analysis_unit="user_id")

    def test_clean_cluster_fixture_passes_with_clustering_note(
        self, cluster_logs: dict[str, pd.DataFrame]
    ) -> None:
        result = check_assignment_integrity(
            self._spec(), cluster_logs["assignments"], cluster_logs["analysis"]
        )
        assert result.status is DiagnosticStatus.PASS
        assert any("cluster on the randomization unit" in n for n in result.notes)

    def test_user_in_two_households_blocks(self, cluster_logs: dict[str, pd.DataFrame]) -> None:
        analysis = cluster_logs["analysis"]
        moved = analysis.iloc[[0]].assign(household_id="h1", arm="treatment")
        analysis = pd.concat([analysis, moved], ignore_index=True)
        result = check_assignment_integrity(self._spec(), cluster_logs["assignments"], analysis)
        assert {"analysis_unit_multi_mapped", "duplicate_analysis_unit"} <= result.codes()


class TestSpec:
    def test_allocations_must_sum_to_one(self) -> None:
        with pytest.raises(ValidationError, match="sum to 1"):
            spec(
                arms=(
                    Arm(name="control", allocation=0.5),
                    Arm(name="treatment", allocation=0.4),
                )
            )

    def test_control_must_be_an_arm(self) -> None:
        with pytest.raises(ValidationError, match="control arm"):
            spec(control_arm="placebo")

    def test_metric_roles_are_exclusive(self) -> None:
        with pytest.raises(ValidationError, match="one role"):
            spec(guardrail_metrics=("converted",))
