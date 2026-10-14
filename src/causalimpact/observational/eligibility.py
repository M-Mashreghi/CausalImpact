"""Observational covariate eligibility from DAG structure and timing metadata (Task 3.1).

Each proposed adjustment variable is classified as:

* **forbidden**: treatment/outcome, known post-treatment or treatment descendant (from
  metadata *or* the DAG, including mediators), declared collider, or unobserved node;
* **review_required**: missing temporal metadata, unknown timing / descendant status, or
  not represented in the DAG;
* **allowed**: known pre-treatment, not a descendant in the DAG, and not otherwise flagged.

Metadata and the DAG are both researcher assumptions; when they disagree the variable is
forbidden and the conflict is reported. The allowed set is then checked as a whole against
the backdoor criterion, because individually acceptable variables can jointly open a
path (e.g. M-bias). Nothing is ever added to the adjustment set automatically.
"""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, ConfigDict

from causalimpact.dags.graph import AdjustmentSet, CausalDAG, VariableFlag, assess_adjustment_set
from causalimpact.domain.variables import CovariateSpec, Eligibility, classify_covariate

FORBIDDING_FLAGS = frozenset(
    {
        VariableFlag.TREATMENT_OR_OUTCOME,
        VariableFlag.MEDIATOR,
        VariableFlag.DESCENDANT_OF_TREATMENT,
        VariableFlag.DECLARED_COLLIDER,
        VariableFlag.UNOBSERVED,
    }
)


class VariableDecision(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    variable: str
    eligibility: Eligibility
    reasons: tuple[str, ...]


class CovariateScreen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    dag_version: str
    treatment: str
    outcome: str
    decisions: tuple[VariableDecision, ...]
    allowed_set_satisfies_backdoor: bool
    open_backdoor_paths: tuple[tuple[str, ...], ...]
    notes: tuple[str, ...]

    def _names(self, level: Eligibility) -> frozenset[str]:
        return frozenset(d.variable for d in self.decisions if d.eligibility is level)

    @property
    def allowed(self) -> frozenset[str]:
        return self._names(Eligibility.ELIGIBLE)

    @property
    def forbidden(self) -> frozenset[str]:
        return self._names(Eligibility.FORBIDDEN)

    @property
    def review_required(self) -> frozenset[str]:
        return self._names(Eligibility.REVIEW_REQUIRED)

    def decision(self, variable: str) -> VariableDecision:
        for d in self.decisions:
            if d.variable == variable:
                return d
        raise KeyError(variable)


def screen_adjustment_candidates(
    dag: CausalDAG,
    treatment: str,
    outcome: str,
    proposed: Iterable[str],
    covariates: Iterable[CovariateSpec],
) -> CovariateScreen:
    metadata = {c.name: c for c in covariates}
    proposed_set = sorted(set(proposed))
    flags = assess_adjustment_set(
        dag,
        AdjustmentSet(
            dag_version=dag.version,
            treatment=treatment,
            outcome=outcome,
            variables=frozenset(proposed_set),
            rationale="eligibility screen",
        ),
    ).variable_flags

    decisions: list[VariableDecision] = []
    for name in proposed_set:
        forbidden: list[str] = []
        review: list[str] = []
        dag_flags = set(flags.get(name, ()))
        for flag in sorted(dag_flags & FORBIDDING_FLAGS):
            forbidden.append(f"DAG: {flag.value.replace('_', ' ')}")
        if VariableFlag.NOT_IN_DAG in dag_flags:
            review.append("not represented in the DAG")

        spec = metadata.get(name)
        if spec is None:
            review.append("no temporal metadata declared")
        else:
            meta = classify_covariate(spec)
            if meta.eligibility is Eligibility.FORBIDDEN:
                forbidden.extend(f"metadata: {r}" for r in meta.reasons)
            elif meta.eligibility is Eligibility.REVIEW_REQUIRED:
                review.extend(f"metadata: {r}" for r in meta.reasons)
            descendant_in_dag = dag_flags & {
                VariableFlag.MEDIATOR,
                VariableFlag.DESCENDANT_OF_TREATMENT,
            }
            if meta.eligibility is Eligibility.ELIGIBLE and descendant_in_dag:
                forbidden.append(
                    "conflict: metadata says pre-treatment but the DAG makes it a "
                    "descendant of treatment; resolve the DAG or the metadata"
                )

        if forbidden:
            decisions.append(
                VariableDecision(
                    variable=name, eligibility=Eligibility.FORBIDDEN, reasons=tuple(forbidden)
                )
            )
        elif review:
            decisions.append(
                VariableDecision(
                    variable=name,
                    eligibility=Eligibility.REVIEW_REQUIRED,
                    reasons=tuple(review),
                )
            )
        else:
            decisions.append(
                VariableDecision(
                    variable=name,
                    eligibility=Eligibility.ELIGIBLE,
                    reasons=("pre-treatment by metadata; not a treatment descendant in the DAG",),
                )
            )

    allowed = frozenset(d.variable for d in decisions if d.eligibility is Eligibility.ELIGIBLE)
    set_assessment = assess_adjustment_set(
        dag,
        AdjustmentSet(
            dag_version=dag.version,
            treatment=treatment,
            outcome=outcome,
            variables=allowed,
            rationale="allowed subset of proposed variables",
        ),
    )
    notes = list(set_assessment.notes)
    if not set_assessment.satisfies_backdoor:
        notes.append(
            "the allowed variables do not satisfy the backdoor criterion on their own; "
            "the design is not identified by this set without further variables or a "
            "different design"
        )
    return CovariateScreen(
        dag_version=dag.version,
        treatment=treatment,
        outcome=outcome,
        decisions=tuple(decisions),
        allowed_set_satisfies_backdoor=set_assessment.satisfies_backdoor,
        open_backdoor_paths=set_assessment.open_backdoor_paths,
        notes=tuple(dict.fromkeys(notes)),
    )
