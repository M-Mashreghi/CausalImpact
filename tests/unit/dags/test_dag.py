"""Task 1.5: known backdoor examples produce the expected safe/unsafe flags."""

from __future__ import annotations

from itertools import chain, combinations

import pytest
from pydantic import ValidationError

from causalimpact.dags import (
    AdjustmentAssessment,
    AdjustmentSet,
    CausalDAG,
    DagNode,
    DagRegistry,
    VariableFlag,
    assess_adjustment_set,
)


def dag(
    edges: str,
    *,
    unobserved: tuple[str, ...] = (),
    colliders: frozenset[str] = frozenset(),
    name: str = "g",
) -> CausalDAG:
    """Build a DAG from ``"A->B, B->C"`` notation."""
    pairs = [tuple(e.strip().split("->")) for e in edges.split(",")]
    names = sorted({n for p in pairs for n in p})
    return CausalDAG(
        name=name,
        nodes=tuple(DagNode(name=n, observed=n not in unobserved) for n in names),
        edges=tuple((a, b) for a, b in pairs),
        declared_colliders=colliders,
    )


def assess(g: CausalDAG, *z: str, t: str = "T", y: str = "Y") -> AdjustmentAssessment:
    adj = AdjustmentSet(
        dag_version=g.version, treatment=t, outcome=y, variables=frozenset(z), rationale="test"
    )
    return assess_adjustment_set(g, adj)


CONFOUNDER = dag("X->T, X->Y, T->Y")
MEDIATED = dag("X->T, X->Y, T->M, M->Y")
DESCENDANT = dag("X->T, X->Y, T->Y, T->D")
M_BIAS = dag("A->T, A->C, B->C, B->Y, T->Y", unobserved=("A", "B"))
M_BIAS_OBSERVED = dag("A->T, A->C, B->C, B->Y, T->Y")
LATENT_CONFOUNDER = dag("U->T, U->Y, T->Y", unobserved=("U",))
# Pearl (2009), Fig. 3.4-style backdoor example with treatment X renamed T.
PEARL = dag("Z1->Z3, Z2->Z3, Z1->T, Z2->Y, Z3->T, Z3->Y, T->W, W->Y")


class TestBackdoorExamples:
    def test_confounder_adjustment_is_safe(self) -> None:
        result = assess(CONFOUNDER, "X")
        assert result.is_safe
        assert result.open_backdoor_paths == ()

    def test_omitting_confounder_leaves_open_path(self) -> None:
        result = assess(CONFOUNDER)
        assert not result.satisfies_backdoor
        assert result.open_backdoor_paths == (("T", "X", "Y"),)

    def test_mediator_flagged(self) -> None:
        result = assess(MEDIATED, "X", "M")
        assert not result.is_safe
        assert result.variable_flags["M"] == (
            VariableFlag.MEDIATOR,
            VariableFlag.DESCENDANT_OF_TREATMENT,
        )
        assert result.variable_flags["X"] == ()
        assert not result.satisfies_backdoor

    def test_non_mediator_descendant_flagged(self) -> None:
        result = assess(DESCENDANT, "X", "D")
        assert result.variable_flags["D"] == (VariableFlag.DESCENDANT_OF_TREATMENT,)
        assert result.unsafe_variables == {"D"}
        assert not result.satisfies_backdoor

    def test_m_bias_empty_set_is_safe(self) -> None:
        assert assess(M_BIAS).is_safe

    def test_m_bias_collider_adjustment_opens_path(self) -> None:
        result = assess(M_BIAS, "C")
        assert not result.satisfies_backdoor
        assert ("T", "A", "C", "B", "Y") in result.open_backdoor_paths
        assert "backdoor path open" in " ".join(result.notes)

    def test_collider_plus_blocking_variable_is_safe(self) -> None:
        assert assess(M_BIAS_OBSERVED, "C", "A").is_safe

    def test_declared_collider_is_flagged_even_if_blocked(self) -> None:
        g = dag("A->T, A->C, B->C, B->Y, T->Y", colliders=frozenset({"C"}))
        result = assess(g, "C", "A")
        assert result.satisfies_backdoor
        assert result.variable_flags["C"] == (VariableFlag.DECLARED_COLLIDER,)
        assert not result.is_safe

    def test_latent_confounder_cannot_be_adjusted(self) -> None:
        assert not assess(LATENT_CONFOUNDER).satisfies_backdoor
        result = assess(LATENT_CONFOUNDER, "U")
        assert result.satisfies_backdoor  # graphically sufficient...
        assert result.variable_flags["U"] == (VariableFlag.UNOBSERVED,)  # ...but unmeasured
        assert not result.is_safe

    def test_variable_outside_dag_is_flagged(self) -> None:
        result = assess(CONFOUNDER, "X", "shoe_size")
        assert result.variable_flags["shoe_size"] == (VariableFlag.NOT_IN_DAG,)

    def test_treatment_in_adjustment_set_is_flagged(self) -> None:
        result = assess(CONFOUNDER, "X", "T")
        assert VariableFlag.TREATMENT_OR_OUTCOME in result.variable_flags["T"]

    @pytest.mark.parametrize(
        ("z", "valid"),
        [
            ((), False),
            (("Z3",), False),  # conditioning on the collider Z3 opens Z1 -> Z3 <- Z2
            (("Z1",), False),
            (("Z1", "Z3"), True),
            (("Z2", "Z3"), True),
            (("Z1", "Z2", "Z3"), True),
            (("Z1", "Z3", "W"), False),  # W is a mediator
        ],
    )
    def test_pearl_backdoor_example(self, z: tuple[str, ...], valid: bool) -> None:
        assert assess(PEARL, *z).satisfies_backdoor is valid

    def test_path_enumeration_agrees_with_d_separation(self) -> None:
        candidates = ["Z1", "Z2", "Z3"]
        subsets = chain.from_iterable(combinations(candidates, k) for k in range(4))
        for z in subsets:
            result = assess(PEARL, *z)
            assert result.satisfies_backdoor == (result.open_backdoor_paths == ()), z

    def test_every_assessment_carries_dag_caveat(self) -> None:
        assert any("untestable assumption" in n for n in assess(CONFOUNDER, "X").notes)


class TestDagStructure:
    def test_cycle_rejected(self) -> None:
        with pytest.raises(ValidationError, match="cycle"):
            dag("A->B, B->C, C->A")

    def test_edge_to_undeclared_node_rejected(self) -> None:
        with pytest.raises(ValidationError, match="undeclared node"):
            CausalDAG(name="g", nodes=(DagNode(name="A"),), edges=(("A", "B"),))

    def test_unknown_declared_collider_rejected(self) -> None:
        with pytest.raises(ValidationError, match="declared colliders"):
            dag("A->B", colliders=frozenset({"Z"}))

    def test_mediators_and_descendants(self) -> None:
        assert PEARL.mediators("T", "Y") == {"W"}
        assert PEARL.descendants("T") == {"W", "Y"}
        assert PEARL.ancestors("T") == {"Z1", "Z2", "Z3"}


class TestVersioning:
    def test_version_ignores_declaration_order(self) -> None:
        a = dag("X->T, X->Y, T->Y")
        b = CausalDAG(
            name="g",
            nodes=tuple(reversed(a.nodes)),
            edges=tuple(reversed(a.edges)),
        )
        assert a.version == b.version
        assert a.version.startswith("dag_")

    def test_changed_structure_changes_version(self) -> None:
        assert dag("X->T, X->Y, T->Y").version != dag("X->T, T->Y").version
        observed = dag("U->T, U->Y, T->Y")
        assert observed.version != LATENT_CONFOUNDER.version

    def test_adjustment_set_version_tracks_dag_and_variables(self) -> None:
        a = assess(CONFOUNDER, "X").adjustment_set_version
        assert a == assess(CONFOUNDER, "X").adjustment_set_version
        assert a != assess(CONFOUNDER).adjustment_set_version
        assert a != assess(dag("X->T, X->Y, T->Y, X->Q"), "X").adjustment_set_version

    def test_adjustment_set_for_other_dag_version_refused(self) -> None:
        adj = AdjustmentSet(
            dag_version=CONFOUNDER.version,
            treatment="T",
            outcome="Y",
            variables=frozenset({"X"}),
            rationale="r",
        )
        with pytest.raises(ValueError, match="was built for"):
            assess_adjustment_set(MEDIATED, adj)

    def test_registry_round_trip_is_reproducible(self) -> None:
        registry = DagRegistry()
        dv = registry.register_dag(PEARL)
        av = registry.register_adjustment_set(
            AdjustmentSet(
                dag_version=dv,
                treatment="T",
                outcome="Y",
                variables=frozenset({"Z1", "Z3"}),
                rationale="blocks all backdoor paths in Pearl example",
            )
        )
        assert registry.register_dag(PEARL) == dv  # idempotent
        restored = DagRegistry.from_json(registry.to_json())
        assert restored.dag(dv) == PEARL
        assert restored.adjustment_set(av).variables == {"Z1", "Z3"}
        assert restored.to_json() == registry.to_json()

    def test_registry_requires_dag_first(self) -> None:
        adj = AdjustmentSet(
            dag_version="dag_missing",
            treatment="T",
            outcome="Y",
            variables=frozenset(),
            rationale="r",
        )
        with pytest.raises(KeyError, match="register DAG"):
            DagRegistry().register_adjustment_set(adj)


def test_registry_json_is_identical_across_hash_seeds() -> None:
    import os
    import subprocess
    import sys

    code = (
        "from tests.unit.dags.test_dag import PEARL, M_BIAS_OBSERVED;"
        "from causalimpact.dags import AdjustmentSet, DagRegistry;"
        "r = DagRegistry();"
        "[r.register_dag(g) for g in (PEARL, M_BIAS_OBSERVED)];"
        "r.register_adjustment_set(AdjustmentSet(dag_version=PEARL.version, treatment='T',"
        "outcome='Y', variables=frozenset({'Z1', 'Z2', 'Z3'}), rationale='r'));"
        "print(r.to_json())"
    )
    outputs = {
        subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            env={**os.environ, "PYTHONHASHSEED": seed},
        ).stdout
        for seed in ("1", "2", "3", "4")
    }
    assert len(outputs) == 1
