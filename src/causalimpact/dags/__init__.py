"""Causal DAG and adjustment-set registry with identification guardrails."""

from causalimpact.dags.graph import (
    AdjustmentAssessment,
    AdjustmentSet,
    CausalDAG,
    DagNode,
    VariableFlag,
    assess_adjustment_set,
)
from causalimpact.dags.registry import DagRegistry

__all__ = [
    "AdjustmentAssessment",
    "AdjustmentSet",
    "CausalDAG",
    "DagNode",
    "DagRegistry",
    "VariableFlag",
    "assess_adjustment_set",
]
