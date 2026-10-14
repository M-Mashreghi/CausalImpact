# CausalImpact — Review Notes v2

The first package had a strong topic list but several specifications were too generic for autonomous implementation. v2 focuses on methodological correctness and task precision.

## Added / strengthened

1. **Causal DAG + adjustment-set registry** — causal covariate selection is now a first-class design artifact.
2. **Sequential experimentation guardrails** — repeated peeking with fixed-horizon inference is explicitly prohibited.
3. **Attrition / missing-outcome diagnostics** — unresolved differential attrition blocks clean experiment decisions.
4. **Ratio / heavy-tailed product metrics** — separated from simple mean/proportion estimators.
5. **Cross-fitting / Double ML** — flexible ML nuisance models now have an inference-safe workflow.
6. **Modern staggered-adoption DiD** — group-time ATT and heterogeneity-robust dynamic effects are explicit tasks.
7. **Reproducibility bundles** — analysis artifacts/config are exportable and rerunnable.
8. **Detailed task-specific DoD** — tasks are no longer generic boilerplate.
9. **Reporting standard** — every report surfaces assumptions, diagnostics, uncertainty and interpretation status.

## Scope control

Advanced methods are marked `Advanced`; a strong portfolio MVP can complete the `Core` track first.

Current task count: **65**.
