"""Assignment, exposure and analysis-unit integrity checks (Task 2.1).

Inputs are kept separate, as they are logged separately in practice:

* ``assignments``: one row per randomization unit with its arm (and optionally time);
* ``exposures`` (optional): exposure events with the arm the unit actually saw;
* ``analysis``: the analysis dataset, carrying both the analysis-unit id and the
  randomization-unit id, plus the arm label used in analysis.

Nothing is repaired or dropped here. Every inconsistency becomes a finding; blocking
findings mean the experiment must not be analysed as randomized until resolved.
"""

from __future__ import annotations

import pandas as pd

from causalimpact.diagnostics.base import (
    DiagnosticResult,
    Finding,
    FindingSeverity,
    examples,
)
from causalimpact.experiments.spec import ExperimentSpec

BLOCKING = FindingSeverity.BLOCKING
WARNING = FindingSeverity.WARNING
NAME = "assignment_integrity"


def _require(df: pd.DataFrame, columns: list[str], label: str) -> list[Finding]:
    missing = [c for c in columns if c not in df.columns]
    if not missing:
        return []
    return [
        Finding(
            code="missing_column",
            severity=BLOCKING,
            message=f"{label} is missing columns {missing}",
            count=len(missing),
        )
    ]


def check_assignment_integrity(
    spec: ExperimentSpec,
    assignments: pd.DataFrame,
    analysis: pd.DataFrame,
    exposures: pd.DataFrame | None = None,
) -> DiagnosticResult:
    rand, arm = spec.randomization_unit, spec.arm_column
    findings: list[Finding] = []

    a_cols = [rand, arm] + ([spec.assignment_time_column] if spec.assignment_time_column else [])
    findings += _require(assignments, a_cols, "assignments")
    an_cols = list(dict.fromkeys([spec.analysis_unit, rand, arm]))
    findings += _require(analysis, an_cols, "analysis data")
    if exposures is not None:
        e_cols = [rand, arm] + ([spec.exposure_time_column] if spec.exposure_time_column else [])
        findings += _require(exposures, e_cols, "exposures")
    if findings:
        return DiagnosticResult(name=NAME, findings=tuple(findings))

    findings += _assignment_findings(spec, assignments)
    assigned = _assigned_arm(spec, assignments)
    if exposures is not None:
        findings += _exposure_findings(spec, assignments, assigned, exposures)
    findings += _analysis_findings(spec, assigned, analysis)

    metrics = {
        "n_assigned_units": int(assigned.size),
        "n_analysis_rows": len(analysis),
        "assigned_by_arm": {k: int(v) for k, v in assigned.value_counts().sort_index().items()},
    }
    notes: list[str] = []
    if spec.analysis_finer_than_randomization:
        notes.append(
            f"analysis unit ({spec.analysis_unit}) differs from randomization unit "
            f"({spec.randomization_unit}); inference must cluster on the randomization unit"
        )
    return DiagnosticResult(
        name=NAME, findings=tuple(findings), metrics=metrics, notes=tuple(notes)
    )


def _assignment_findings(spec: ExperimentSpec, assignments: pd.DataFrame) -> list[Finding]:
    rand, arm = spec.randomization_unit, spec.arm_column
    out: list[Finding] = []
    missing = assignments[rand].isna() | assignments[arm].isna()
    if missing.any():
        out.append(
            Finding(
                code="missing_assignment_field",
                severity=BLOCKING,
                message="assignment rows with missing unit id or arm",
                count=int(missing.sum()),
            )
        )
    valid = assignments.loc[~missing]
    unknown = valid.loc[~valid[arm].isin(spec.arm_names)]
    if len(unknown):
        out.append(
            Finding(
                code="unknown_arm",
                severity=BLOCKING,
                message=f"assignments to arms outside the design {list(spec.arm_names)}",
                count=len(unknown),
                examples=examples(unknown[arm]),
            )
        )
    arms_per_unit = valid.groupby(rand)[arm].nunique()
    conflicting = arms_per_unit[arms_per_unit > 1]
    if len(conflicting):
        out.append(
            Finding(
                code="conflicting_assignment",
                severity=BLOCKING,
                message="randomization units assigned to more than one arm (cross-arm "
                "contamination)",
                count=len(conflicting),
                examples=examples(conflicting.index),
            )
        )
    duplicated = valid.duplicated(subset=[rand, arm], keep="first")
    if duplicated.any():
        out.append(
            Finding(
                code="duplicate_assignment",
                severity=WARNING,
                message="repeated assignment records with the same arm (logging duplicates)",
                count=int(duplicated.sum()),
                examples=examples(valid.loc[duplicated, rand]),
            )
        )
    return out


def _assigned_arm(spec: ExperimentSpec, assignments: pd.DataFrame) -> pd.Series:
    """Arm per unit for units with exactly one known arm; conflicting units are excluded."""
    rand, arm = spec.randomization_unit, spec.arm_column
    valid = assignments.dropna(subset=[rand, arm])
    valid = valid.loc[valid[arm].isin(spec.arm_names)]
    n_arms = valid.groupby(rand)[arm].nunique()
    consistent = valid.loc[valid[rand].isin(n_arms[n_arms == 1].index)]
    return consistent.drop_duplicates(subset=[rand]).set_index(rand)[arm]


def _exposure_findings(
    spec: ExperimentSpec,
    assignments: pd.DataFrame,
    assigned: pd.Series,
    exposures: pd.DataFrame,
) -> list[Finding]:
    rand, arm = spec.randomization_unit, spec.arm_column
    out: list[Finding] = []
    known = exposures.loc[exposures[rand].isin(assigned.index)]
    unassigned = exposures.loc[~exposures[rand].isin(assignments[rand])]
    if len(unassigned):
        out.append(
            Finding(
                code="exposure_without_assignment",
                severity=BLOCKING,
                message="exposure events for units that were never assigned",
                count=int(unassigned[rand].nunique()),
                examples=examples(unassigned[rand]),
            )
        )
    wrong = known.loc[known[arm].to_numpy() != assigned.loc[known[rand]].to_numpy()]
    if len(wrong):
        out.append(
            Finding(
                code="cross_arm_exposure",
                severity=BLOCKING,
                message="units exposed to an arm other than the one they were assigned",
                count=int(wrong[rand].nunique()),
                examples=examples(wrong[rand]),
            )
        )
    a_time, e_time = spec.assignment_time_column, spec.exposure_time_column
    if a_time and e_time:
        first_assigned = assignments.groupby(rand)[a_time].min()
        joined = known.assign(_assigned_at=first_assigned.loc[known[rand]].to_numpy())
        early = joined.loc[joined[e_time] < joined["_assigned_at"]]
        if len(early):
            out.append(
                Finding(
                    code="exposure_before_assignment",
                    severity=BLOCKING,
                    message="exposure logged before the unit was assigned",
                    count=int(early[rand].nunique()),
                    examples=examples(early[rand]),
                )
            )
    return out


def _analysis_findings(
    spec: ExperimentSpec, assigned: pd.Series, analysis: pd.DataFrame
) -> list[Finding]:
    rand, arm, unit = spec.randomization_unit, spec.arm_column, spec.analysis_unit
    out: list[Finding] = []
    dup_units = analysis[unit].duplicated(keep="first")
    if dup_units.any():
        out.append(
            Finding(
                code="duplicate_analysis_unit",
                severity=BLOCKING,
                message="analysis units appearing more than once",
                count=int(dup_units.sum()),
                examples=examples(analysis.loc[dup_units, unit]),
            )
        )
    if spec.analysis_finer_than_randomization:
        parents = analysis.groupby(unit)[rand].nunique()
        multi = parents[parents > 1]
        if len(multi):
            out.append(
                Finding(
                    code="analysis_unit_multi_mapped",
                    severity=BLOCKING,
                    message="analysis units mapped to more than one randomization unit",
                    count=len(multi),
                    examples=examples(multi.index),
                )
            )
    not_assigned = analysis.loc[~analysis[rand].isin(assigned.index)]
    if len(not_assigned):
        out.append(
            Finding(
                code="analysis_unit_not_assigned",
                severity=BLOCKING,
                message="analysis rows whose randomization unit has no valid assignment",
                count=len(not_assigned),
                examples=examples(not_assigned[rand]),
            )
        )
    matched = analysis.loc[analysis[rand].isin(assigned.index)]
    mismatch = matched.loc[matched[arm].to_numpy() != assigned.loc[matched[rand]].to_numpy()]
    if len(mismatch):
        out.append(
            Finding(
                code="arm_mismatch",
                severity=BLOCKING,
                message="analysis arm label differs from the assigned arm (ITT requires "
                "analysing units as assigned)",
                count=len(mismatch),
                examples=examples(mismatch[rand]),
            )
        )
    missing_units = set(assigned.index) - set(analysis[rand])
    if missing_units:
        out.append(
            Finding(
                code="assigned_not_analyzed",
                severity=WARNING,
                message="assigned randomization units absent from the analysis data; run "
                "attrition diagnostics",
                count=len(missing_units),
                examples=examples(missing_units),
            )
        )
    return out
