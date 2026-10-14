"""Versioned storage of DAGs and the adjustment sets derived from them."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalimpact.dags.graph import AdjustmentSet, CausalDAG


class _Snapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dags: tuple[CausalDAG, ...]
    adjustment_sets: tuple[AdjustmentSet, ...]


class DagRegistry:
    """Content-addressed registry: an object's version is the hash of its content.

    Registering the same content twice returns the same version; changed content always
    yields a new version, so an AnalysisRun's stored DAG/adjustment-set versions identify
    exactly what was assumed.
    """

    def __init__(self) -> None:
        self._dags: dict[str, CausalDAG] = {}
        self._sets: dict[str, AdjustmentSet] = {}

    def register_dag(self, dag: CausalDAG) -> str:
        self._dags.setdefault(dag.version, dag)
        return dag.version

    def register_adjustment_set(self, adjustment: AdjustmentSet) -> str:
        if adjustment.dag_version not in self._dags:
            raise KeyError(f"register DAG {adjustment.dag_version} before its adjustment sets")
        self._sets.setdefault(adjustment.version, adjustment)
        return adjustment.version

    def dag(self, version: str) -> CausalDAG:
        return self._dags[version]

    def adjustment_set(self, version: str) -> AdjustmentSet:
        return self._sets[version]

    def adjustment_sets_for(self, dag_version: str) -> tuple[AdjustmentSet, ...]:
        return tuple(
            sorted(
                (s for s in self._sets.values() if s.dag_version == dag_version),
                key=lambda s: s.version,
            )
        )

    def to_json(self) -> str:
        snapshot = _Snapshot(
            dags=tuple(self._dags[v] for v in sorted(self._dags)),
            adjustment_sets=tuple(self._sets[v] for v in sorted(self._sets)),
        )
        return snapshot.model_dump_json()

    @classmethod
    def from_json(cls, payload: str | bytes) -> DagRegistry:
        snapshot = _Snapshot.model_validate_json(payload)
        registry = cls()
        for dag in snapshot.dags:
            registry.register_dag(dag)
        for adjustment in snapshot.adjustment_sets:
            registry.register_adjustment_set(adjustment)
        return registry
