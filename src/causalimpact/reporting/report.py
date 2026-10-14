"""Assumption-aware report generator (Task 6.6, REPORTING_STANDARD.md).

``build_report`` turns an ``AnalysisResult`` (plus optional robustness artifacts) into a
structured ``Report`` with every required section; ``render_markdown`` renders it.

Rules enforced here:

* every section is always present; anything not run is stated as "not run", never
  silently omitted;
* failed and warning diagnostics are listed with their findings;
* untestable assumptions and assumptions with concerns stay visible;
* the interpretation label is exactly the one computed by the analysis service; this
  module never upgrades it (statistical significance alone is not a causal label).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from causalimpact.domain.assumptions import Testability
from causalimpact.sensitivity.specification import SpecificationReport
from causalimpact.sensitivity.trimming import TrimmingReport
from causalimpact.services.analysis import AnalysisResult

REQUIRED_SECTIONS = (
    "Interpretation status",
    "Design",
    "Result",
    "Diagnostics",
    "Robustness",
    "Assumptions",
    "Limitations",
    "Reproducibility",
    "Method references",
)

METHOD_REFERENCES = {
    "difference_in_means": "Neyman (1923); Welch (1947) for the t interval",
    "difference_in_proportions": "Unpooled Wald interval for a difference in proportions",
    "lin_regression_adjustment": "Lin (2013), Agnostic notes on regression adjustments",
    "cuped": "Deng, Xu, Kohavi & Walker (2013), CUPED",
    "aipw": "Robins, Rotnitzky & Zhao (1994); Hahn (1998) for the ATT",
    "hajek_weighting": "Horvitz & Thompson (1952); Hajek (1971); Li, Morgan & Zaslavsky (2018)",
    "outcome_regression": "Robins (1986), g-computation",
    "did": "Difference-in-differences under parallel trends; Callaway & Sant'Anna (2021) "
    "for staggered adoption",
    "sample_ratio_mismatch": "Fabijan et al. (2019), sample ratio mismatch diagnosis",
}


class Section(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    lines: tuple[str, ...]


class Report(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str
    run_id: str
    interpretation: str
    sections: tuple[Section, ...]

    def section(self, title: str) -> Section:
        for s in self.sections:
            if s.title == title:
                return s
        raise KeyError(title)


def _fmt(x: float | None, digits: int = 4) -> str:
    return "n/a" if x is None else f"{x:.{digits}g}"


def build_report(
    result: AnalysisResult,
    *,
    specifications: SpecificationReport | None = None,
    trimming: TrimmingReport | None = None,
) -> Report:
    design, estimand, est = result.design, result.estimand, result.estimate
    sections: list[Section] = []

    sections.append(
        Section(
            title="Interpretation status",
            lines=(f"**{result.interpretation.value}**", *(f"- {r}" for r in result.reasons)),
        )
    )
    sections.append(
        Section(
            title="Design",
            lines=(
                f"- Research question: {design.research_question}",
                f"- Study design: {design.design_family.value}",
                f"- Treatment: {design.treatment}",
                f"- Outcome: {design.outcome}",
                f"- Population: {estimand.target_population.name}: "
                f"{estimand.target_population.description}",
                f"- Estimand: {estimand.type} ({estimand.estimand_id}), averaged over "
                f"{estimand.averaged_over}; scale {estimand.scale}",
                f"- DAG version: {design.dag_version or 'none declared'}",
                f"- Adjustment set version: {design.adjustment_set_version or 'none declared'}",
            ),
        )
    )
    if est is None:
        result_lines: tuple[str, ...] = (
            "No estimate is reported: estimation was withheld or failed (see interpretation "
            "status).",
        )
    else:
        n_eff = est.details.get("weights")
        result_lines = (
            f"- Point estimate: {_fmt(est.estimate)} (units of {design.outcome}, {estimand.scale})",
            f"- {est.confidence_level:.0%} interval: [{_fmt(est.ci_lower)}, {_fmt(est.ci_upper)}]",
            f"- Standard error: {_fmt(est.std_error)}; p-value: {_fmt(est.p_value, 3)}",
            f"- Inference method: {est.inference_method}",
            f"- Estimator: {est.estimator}",
            f"- Sample size: {est.n_units} (treated {est.n_treated}, control {est.n_control})",
            *(["- Effective sample sizes: see weight diagnostics"] if n_eff else []),
        )
    sections.append(Section(title="Result", lines=result_lines))

    diag_lines: list[str] = []
    for d in result.diagnostics:
        required = "required" if d.name in result.required_diagnostics else "optional"
        diag_lines.append(f"- {d.name} ({required}): **{d.status.value}**")
        diag_lines.extend(f"  - [{f.severity}] {f.code}: {f.message}" for f in d.findings)
    if est is not None:
        weight_findings = est.details.get("weight_findings")
        for f in weight_findings if isinstance(weight_findings, list) else []:
            if isinstance(f, dict):
                diag_lines.append(
                    f"- weights: [{f.get('severity')}] {f.get('code')}: {f.get('message')}"
                )
        if est.details.get("overlap_status"):
            diag_lines.append(f"- overlap (attached to estimate): {est.details['overlap_status']}")
    sections.append(Section(title="Diagnostics", lines=tuple(diag_lines) or ("- none run",)))

    robust: list[str] = []
    if specifications is None:
        robust.append("- Alternative specifications: not run")
    else:
        s = specifications.summary
        robust.append(
            f"- Alternative specifications ({s['n_declared']} declared, {s['n_succeeded']} "
            f"succeeded, grid {specifications.grid_fingerprint[:19]}…): estimates from "
            f"{s.get('min_estimate', 'n/a')} to {s.get('max_estimate', 'n/a')}"
        )
        robust.extend(
            f"  - {o.label}: {o.status.value}"
            + (f" {_fmt(o.estimate.estimate)}" if o.estimate else f" ({o.error})")
            for o in specifications.outcomes
        )
    if trimming is None:
        robust.append("- Trimming / weighting sensitivity: not run")
    else:
        robust.append("- Trimming / weighting sensitivity:")
        robust.extend(
            f"  - {o.policy.label}: estimand {o.estimand.estimand_id}"
            + (" (population restricted)" if o.population_changed else "")
            + (f", estimate {_fmt(o.estimate.estimate)}" if o.estimate else f", {o.error}")
            for o in trimming.outcomes
        )
    robust.append("- Placebo / falsification checks: not run")
    robust.append("- Unmeasured-confounding sensitivity: not run")
    sections.append(Section(title="Robustness", lines=tuple(robust)))

    sections.append(
        Section(
            title="Assumptions",
            lines=tuple(
                f"- {a.key} [{a.testability.value}, {a.status.value}]: {a.statement}"
                + (f" Justification: {a.justification}" if a.justification else "")
                for a in result.assumptions
            )
            or ("- none declared",),
        )
    )
    untestable = [a.key for a in result.assumptions if a.testability is Testability.UNTESTABLE]
    sections.append(
        Section(
            title="Limitations",
            lines=(
                *(f"- {line}" for line in result.limitations),
                f"- Untestable identifying assumptions remain assumptions: "
                f"{', '.join(untestable) or 'none'}",
                "- A statistically significant estimate is not by itself evidence of causality.",
            ),
        )
    )
    run = result.run
    sections.append(
        Section(
            title="Reproducibility",
            lines=(
                f"- AnalysisRun: {run.run_id} (status {run.status.value})",
                f"- Specification fingerprint: {result.run_fingerprint}",
                f"- Design: {run.design_id} v{run.design_version} ({run.design_content_hash})",
                f"- Dataset version: {run.dataset_version}",
                f"- Seed: {run.seed}; confidence level: {run.confidence_level}",
                f"- Code version: {run.code_version}",
            ),
        )
    )
    used = {est.estimator if est else run.estimator} | {d.name for d in result.diagnostics}
    refs = sorted(
        {ref for key, ref in METHOD_REFERENCES.items() for name in used if name.startswith(key)}
    )
    sections.append(
        Section(title="Method references", lines=tuple(f"- {r}" for r in refs) or ("- none",))
    )
    return Report(
        title=design.title,
        run_id=run.run_id,
        interpretation=result.interpretation.value,
        sections=tuple(sections),
    )


def render_markdown(report: Report) -> str:
    parts = [f"# {report.title}", ""]
    for section in report.sections:
        parts += [f"## {section.title}", "", *section.lines, ""]
    return "\n".join(parts)
