"""Causal DAGs, content-derived versions, and adjustment-set guardrails.

A DAG is a researcher's documented causal assumptions. These checks can show that an
adjustment set is *inconsistent* with the declared DAG; they cannot show that the DAG is
correct (dag-identification rules).

The backdoor criterion (Pearl) is checked exactly:

1. no adjustment variable is a descendant of the treatment, and
2. the adjustment set d-separates treatment and outcome once the treatment's outgoing
   edges are removed.

d-separation uses the moralised ancestral graph construction. Open backdoor paths are
also enumerated (up to a limit) so that a failed check can be explained.
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from causalimpact.domain.study_design import NonBlankStr

MAX_EXPLAINED_PATHS = 50


def _digest(payload: object, prefix: str) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return f"{prefix}_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


class DagNode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    observed: bool = True
    description: NonBlankStr | None = None


class CausalDAG(BaseModel):
    """A directed acyclic graph of causal assumptions with a content-derived version."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: NonBlankStr
    nodes: tuple[DagNode, ...]
    edges: tuple[tuple[NonBlankStr, NonBlankStr], ...]
    declared_colliders: frozenset[NonBlankStr] = Field(default_factory=frozenset)

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        names = [n.name for n in self.nodes]
        if len(names) != len(set(names)):
            raise ValueError("duplicate node names")
        known = set(names)
        for src, dst in self.edges:
            if src not in known or dst not in known:
                raise ValueError(f"edge {src}->{dst} references an undeclared node")
            if src == dst:
                raise ValueError(f"self-loop on {src}")
        if len(set(self.edges)) != len(self.edges):
            raise ValueError("duplicate edges")
        if unknown := self.declared_colliders - known:
            raise ValueError(f"declared colliders not in DAG: {sorted(unknown)}")
        if self._has_cycle():
            raise ValueError("graph contains a directed cycle")
        return self

    # -- structure -----------------------------------------------------------------

    @property
    def node_names(self) -> frozenset[str]:
        return frozenset(n.name for n in self.nodes)

    @property
    def unobserved(self) -> frozenset[str]:
        return frozenset(n.name for n in self.nodes if not n.observed)

    def parents(self, node: str) -> frozenset[str]:
        return frozenset(s for s, d in self.edges if d == node)

    def children(self, node: str) -> frozenset[str]:
        return frozenset(d for s, d in self.edges if s == node)

    def descendants(self, node: str) -> frozenset[str]:
        return self._reach([node], self.children) - {node}

    def ancestors(self, node: str) -> frozenset[str]:
        return self._reach([node], self.parents) - {node}

    def mediators(self, treatment: str, outcome: str) -> frozenset[str]:
        """Nodes on a directed path from treatment to outcome."""
        return self.descendants(treatment) & self.ancestors(outcome)

    def _reach(self, start: Iterable[str], step: Callable[[str], frozenset[str]]) -> frozenset[str]:
        seen = set(start)
        queue = deque(seen)
        while queue:
            for nxt in step(queue.popleft()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return frozenset(seen)

    def _has_cycle(self) -> bool:
        indegree = {n.name: 0 for n in self.nodes}
        for _, dst in self.edges:
            indegree[dst] += 1
        queue = deque(n for n, d in indegree.items() if d == 0)
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for child in self.children(node):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        return visited != len(indegree)

    # -- versioning ----------------------------------------------------------------

    def canonical(self) -> dict[str, object]:
        return {
            "name": self.name,
            "nodes": sorted((n.name, n.observed, n.description or "") for n in self.nodes),
            "edges": sorted(self.edges),
            "declared_colliders": sorted(self.declared_colliders),
        }

    @property
    def version(self) -> str:
        """Content hash: identical graphs get identical versions regardless of ordering."""
        return _digest(self.canonical(), "dag")

    # -- d-separation ----------------------------------------------------------------

    def d_separated(
        self,
        xs: Iterable[str],
        ys: Iterable[str],
        given: Iterable[str],
        *,
        edges: tuple[tuple[str, str], ...] | None = None,
    ) -> bool:
        """True if every node in ``xs`` is d-separated from every node in ``ys`` given ``given``."""
        edge_list = self.edges if edges is None else edges
        x, y, z = set(xs), set(ys), set(given)
        parents: dict[str, set[str]] = {}
        for s, d in edge_list:
            parents.setdefault(d, set()).add(s)
        # Ancestral set of x, y and z.
        relevant = set(x | y | z)
        queue = deque(relevant)
        while queue:
            for p in parents.get(queue.popleft(), ()):
                if p not in relevant:
                    relevant.add(p)
                    queue.append(p)
        # Moralise: undirected parent-child edges plus edges between co-parents.
        adjacency: dict[str, set[str]] = {n: set() for n in relevant}
        for child in relevant:
            ps = [p for p in parents.get(child, ()) if p in relevant]
            for p in ps:
                adjacency[p].add(child)
                adjacency[child].add(p)
            for i, a in enumerate(ps):
                for b in ps[i + 1 :]:
                    adjacency[a].add(b)
                    adjacency[b].add(a)
        # Remove conditioning set and test connectivity.
        seen = set(x - z)
        queue = deque(seen)
        while queue:
            for nxt in adjacency[queue.popleft()]:
                if nxt in z or nxt in seen:
                    continue
                if nxt in y:
                    return False
                seen.add(nxt)
                queue.append(nxt)
        return True

    def backdoor_edges(self, treatment: str) -> tuple[tuple[str, str], ...]:
        """Edges with the treatment's outgoing edges removed."""
        return tuple(e for e in self.edges if e[0] != treatment)

    def open_backdoor_paths(
        self, treatment: str, outcome: str, given: Iterable[str]
    ) -> list[list[str]]:
        """Backdoor paths (first edge into treatment) left open by ``given``."""
        z = set(given)
        z_and_ancestors = set(z)
        for node in z:
            z_and_ancestors |= self.ancestors(node)
        neighbours: dict[str, set[str]] = {n: set() for n in self.node_names}
        for s, d in self.edges:
            neighbours[s].add(d)
            neighbours[d].add(s)
        edge_set = set(self.edges)
        open_paths: list[list[str]] = []

        def blocked(path: list[str]) -> bool:
            for a, b, c in zip(path, path[1:], path[2:], strict=False):
                collider = (a, b) in edge_set and (c, b) in edge_set
                if collider and b not in z_and_ancestors:
                    return True
                if not collider and b in z:
                    return True
            return False

        def walk(path: list[str]) -> None:
            if len(open_paths) >= MAX_EXPLAINED_PATHS:
                return
            last = path[-1]
            if last == outcome:
                if not blocked(path):
                    open_paths.append(list(path))
                return
            for nxt in sorted(neighbours[last]):
                if nxt not in path:
                    walk([*path, nxt])

        for parent in sorted(self.parents(treatment)):
            walk([treatment, parent])
        return open_paths


class VariableFlag(StrEnum):
    NOT_IN_DAG = "not_in_dag"
    UNOBSERVED = "unobserved"
    TREATMENT_OR_OUTCOME = "treatment_or_outcome"
    MEDIATOR = "mediator"
    DESCENDANT_OF_TREATMENT = "descendant_of_treatment"
    DECLARED_COLLIDER = "declared_collider"


class AdjustmentSet(BaseModel):
    """A proposed adjustment set, bound to the exact DAG version it was derived from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dag_version: NonBlankStr
    treatment: NonBlankStr
    outcome: NonBlankStr
    variables: frozenset[NonBlankStr]
    rationale: NonBlankStr

    @property
    def version(self) -> str:
        return _digest(
            {
                "dag_version": self.dag_version,
                "treatment": self.treatment,
                "outcome": self.outcome,
                "variables": sorted(self.variables),
            },
            "adjset",
        )


class AdjustmentAssessment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dag_version: str
    adjustment_set_version: str
    treatment: str
    outcome: str
    variable_flags: dict[str, tuple[VariableFlag, ...]]
    satisfies_backdoor: bool
    open_backdoor_paths: tuple[tuple[str, ...], ...]
    notes: tuple[str, ...]

    @property
    def is_safe(self) -> bool:
        """No variable is flagged and the backdoor criterion holds in the declared DAG."""
        return self.satisfies_backdoor and not any(self.variable_flags.values())

    @property
    def unsafe_variables(self) -> frozenset[str]:
        return frozenset(v for v, flags in self.variable_flags.items() if flags)


CAVEAT = "Checked against the declared DAG only; the DAG itself is an untestable assumption."


def assess_adjustment_set(dag: CausalDAG, adjustment: AdjustmentSet) -> AdjustmentAssessment:
    if adjustment.dag_version != dag.version:
        raise ValueError(
            f"adjustment set was built for {adjustment.dag_version}, not DAG {dag.version}"
        )
    t, y = adjustment.treatment, adjustment.outcome
    for role in (t, y):
        if role not in dag.node_names:
            raise ValueError(f"{role!r} is not a node of the DAG")
    descendants = dag.descendants(t)
    mediators = dag.mediators(t, y)
    flags: dict[str, tuple[VariableFlag, ...]] = {}
    for var in sorted(adjustment.variables):
        found: list[VariableFlag] = []
        if var not in dag.node_names:
            found.append(VariableFlag.NOT_IN_DAG)
        else:
            if var in (t, y):
                found.append(VariableFlag.TREATMENT_OR_OUTCOME)
            if var in dag.unobserved:
                found.append(VariableFlag.UNOBSERVED)
            if var in mediators:
                found.append(VariableFlag.MEDIATOR)
            if var in descendants:
                found.append(VariableFlag.DESCENDANT_OF_TREATMENT)
            if var in dag.declared_colliders:
                found.append(VariableFlag.DECLARED_COLLIDER)
        flags[var] = tuple(found)

    in_dag = {v for v in adjustment.variables if v in dag.node_names} - {t, y}
    no_descendants = not (in_dag & descendants)
    blocks = dag.d_separated([t], [y], in_dag, edges=dag.backdoor_edges(t))
    paths = dag.open_backdoor_paths(t, y, in_dag)
    notes = [CAVEAT]
    if not blocks:
        notes.append("adjustment set leaves at least one backdoor path open")
    if len(paths) >= MAX_EXPLAINED_PATHS:
        notes.append(f"open-path listing truncated at {MAX_EXPLAINED_PATHS}")
    return AdjustmentAssessment(
        dag_version=dag.version,
        adjustment_set_version=adjustment.version,
        treatment=t,
        outcome=y,
        variable_flags=flags,
        satisfies_backdoor=blocks and no_descendants,
        open_backdoor_paths=tuple(tuple(p) for p in paths),
        notes=tuple(notes),
    )
