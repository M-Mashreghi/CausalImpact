"""Run a whole study from a CSV file and a JSON study file.

The study file states, in one place, everything the platform needs: the estimand, the
design (question, population, treatment, outcome, identification fields), a justification
for each required assumption, an optional DAG and adjustment set, and the run
specification (estimator and diagnostics). ``run_study`` validates the design (fail
closed), runs the analysis and writes a reproducibility bundle with the report.

    python scripts/run_analysis.py --data my.csv --study my_study.json --out results/
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from causalimpact.dags import AdjustmentSet, CausalDAG, DagRegistry
from causalimpact.design import DesignReadinessValidator, default_assumptions
from causalimpact.domain import (
    DesignNotReadyError,
    DesignStatus,
    Estimand,
    EstimandRegistry,
    StudyDesign,
)
from causalimpact.services.analysis import AnalysisResult, AnalysisService
from causalimpact.services.registry import export_bundle
from causalimpact.services.run_spec import RunSpec, execute


class StudyFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    estimand: Estimand
    design: dict[str, Any] = Field(
        description="StudyDesign fields except ids, status, estimand/DAG versions and assumptions"
    )
    assumption_justifications: dict[str, str] = Field(default_factory=dict)
    dag: CausalDAG | None = None
    adjustment_set: list[str] | None = None
    run: RunSpec


@dataclass(frozen=True)
class StudyOutcome:
    result: AnalysisResult | None
    problems: tuple[str, ...]
    bundle: Path | None


def build_study(study: StudyFile) -> tuple[StudyDesign, AnalysisService]:
    estimands, dags = EstimandRegistry([study.estimand]), DagRegistry()
    fields = dict(study.design)
    reserved = {"design_id", "version", "status", "status_history", "created_at", "estimand_id",
                "dag_version", "adjustment_set_version", "assumptions"}  # fmt: skip
    if bad := reserved & fields.keys():
        raise ValueError(f"set these through the study file, not 'design': {sorted(bad)}")
    if study.dag is not None:
        fields["dag_version"] = dags.register_dag(study.dag)
        if study.adjustment_set is not None:
            adjustment = AdjustmentSet(
                dag_version=study.dag.version,
                treatment=study.estimand.treatment,
                outcome=study.estimand.outcome,
                variables=frozenset(study.adjustment_set),
                rationale="declared in the study file",
            )
            fields["adjustment_set_version"] = dags.register_adjustment_set(adjustment)
    elif study.adjustment_set is not None:
        raise ValueError("an adjustment set needs a DAG")
    base = StudyDesign(**fields, estimand_id=study.estimand.estimand_id)
    assumptions = tuple(
        a.justify(study.assumption_justifications[a.key])
        if study.assumption_justifications.get(a.key, "").strip()
        else a
        for a in default_assumptions(base.design_family)
    )
    design = StudyDesign.model_validate({**base.model_dump(), "assumptions": assumptions})
    return design, AnalysisService(estimands, dags)


def run_study(study: StudyFile, data: pd.DataFrame, out: Path | None = None) -> StudyOutcome:
    design, service = build_study(study)
    validator = DesignReadinessValidator(service.estimands, service.dags)
    validated = design.transition(DesignStatus.VALIDATED, reason="study file")
    try:
        ready = validated.transition(
            DesignStatus.ANALYSIS_READY, reason="study file", readiness_check=validator
        )
    except DesignNotReadyError as exc:
        return StudyOutcome(result=None, problems=tuple(str(exc).split("; ")), bundle=None)
    result = execute(service, ready, study.run, data)
    bundle = None
    if out is not None:
        bundle = export_bundle(result, study.run, data, service, out)
    return StudyOutcome(result=result, problems=(), bundle=bundle)
