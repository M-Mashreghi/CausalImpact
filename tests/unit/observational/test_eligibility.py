"""Task 3.1: mediator / collider / post-treatment fixtures are flagged."""

from __future__ import annotations

import pytest

from causalimpact.dags import CausalDAG, DagNode
from causalimpact.domain import CovariateDType, CovariateSpec, Eligibility, TriState
from causalimpact.observational.eligibility import CovariateScreen, screen_adjustment_candidates

T_, F_, U_ = TriState.TRUE, TriState.FALSE, TriState.UNKNOWN

EDGES = [
    ("L", "T"), ("L", "Y"),  # confounder
    ("T", "M"), ("M", "Y"), ("T", "Y"),  # mediator
    ("T", "P"),  # post-treatment, not on a causal path to Y
    ("A", "T"), ("A", "C"), ("B", "C"), ("B", "Y"),  # M-bias structure
    ("T", "S"), ("Y", "S"),  # selection collider
    ("U", "T"), ("U", "Y"),  # unmeasured confounder
]  # fmt: skip
DAG = CausalDAG(
    name="screen",
    nodes=tuple(DagNode(name=n, observed=n != "U") for n in sorted({x for e in EDGES for x in e})),
    edges=tuple(EDGES),
    declared_colliders=frozenset({"S"}),
)


def meta(name: str, pre: TriState, desc: TriState) -> CovariateSpec:
    return CovariateSpec(
        name=name,
        dtype=CovariateDType.NUMERIC,
        measurement_time="baseline" if pre is T_ else None,
        pre_treatment=pre,
        descendant_of_treatment=desc,
    )


METADATA = [
    meta("L", T_, F_),
    meta("M", T_, F_),  # metadata wrongly claims pre-treatment
    meta("P", F_, T_),
    meta("A", T_, F_),
    meta("B", T_, F_),
    meta("C", T_, F_),
    meta("S", F_, U_),
    meta("U", T_, F_),
    meta("Q", T_, F_),  # not in DAG
    meta("W", U_, U_),  # unknown timing (not in DAG either)
]


def screen(*proposed: str) -> CovariateScreen:
    return screen_adjustment_candidates(DAG, "T", "Y", proposed, METADATA)


@pytest.mark.parametrize(
    ("variable", "expected", "reason"),
    [
        ("L", Eligibility.ELIGIBLE, "pre-treatment"),
        ("M", Eligibility.FORBIDDEN, "mediator"),
        ("P", Eligibility.FORBIDDEN, "descendant of treatment"),
        ("S", Eligibility.FORBIDDEN, "declared collider"),
        ("U", Eligibility.FORBIDDEN, "unobserved"),
        ("T", Eligibility.FORBIDDEN, "treatment or outcome"),
        ("Q", Eligibility.REVIEW_REQUIRED, "not represented in the DAG"),
        ("W", Eligibility.REVIEW_REQUIRED, "unknown measurement timing"),
        ("R", Eligibility.REVIEW_REQUIRED, "no temporal metadata"),
    ],
)
def test_variable_classification(variable: str, expected: Eligibility, reason: str) -> None:
    decision = screen(variable).decision(variable)
    assert decision.eligibility is expected
    assert any(reason in r for r in decision.reasons), decision.reasons


def test_metadata_dag_conflict_is_reported() -> None:
    reasons = screen("M").decision("M").reasons
    assert any(r.startswith("conflict:") for r in reasons)


def test_post_treatment_by_metadata_alone_is_forbidden() -> None:
    reasons = screen("P").decision("P").reasons
    assert "metadata: measured after treatment" in reasons


def test_sets_partition_the_proposal() -> None:
    result = screen("L", "M", "P", "Q", "R", "S")
    assert result.allowed == {"L"}
    assert result.forbidden == {"M", "P", "S"}
    assert result.review_required == {"Q", "R"}


def test_m_bias_collider_is_individually_allowed_but_set_fails() -> None:
    result = screen("C")
    assert result.allowed == {"C"}
    assert not result.allowed_set_satisfies_backdoor
    assert ("T", "A", "C", "B", "Y") in result.open_backdoor_paths
    assert any("not identified by this set" in n for n in result.notes)


def test_unmeasured_confounder_leaves_design_unidentified() -> None:
    result = screen("L", "A", "B")
    assert result.allowed == {"L", "A", "B"}
    assert not result.allowed_set_satisfies_backdoor  # T <- U -> Y stays open
    assert ("T", "U", "Y") in result.open_backdoor_paths


def test_nothing_is_added_automatically() -> None:
    result = screen("L")
    assert {d.variable for d in result.decisions} == {"L"}
