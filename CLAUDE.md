# CausalImpact — Claude Code Instructions

CausalImpact is a research-oriented causal inference and experimentation platform.

## Source of truth

Before implementation, read:

1. `docs/PROJECT_PHASES_AND_TASKS.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DESIGN_PROTOCOL.md`
4. `docs/CAUSAL_ASSUMPTIONS.md`
5. `docs/TASKS.md`
6. applicable `.claude/rules/*.md`

Do not invent requirements that conflict with these documents.

## Task workflow

For every task:

1. Read the exact scope and Definition of Done.
2. Inspect current code before editing.
3. Implement only that task.
4. Add or update tests.
5. Run the relevant test suite.
6. Fix failures before marking complete.
7. Update `docs/TASKS.md` and `docs/PROJECT_PHASES_AND_TASKS.md` only after verification.
8. Do not start the next task unless explicitly asked.

## Estimand first

Define the target estimand before selecting an estimator.

Examples: ATE, ATT, ATC, CATE, ITT.

Never silently switch estimands because an estimator is easier to implement.

## Design before estimation

A causal analysis must define:

- treatment,
- outcome,
- target population,
- assignment / exposure mechanism,
- causal graph or equivalent design rationale,
- identification assumptions,
- allowed pre-treatment covariates,
- forbidden or suspect post-treatment variables.

## No post-treatment adjustment by default

Variables affected by treatment must not enter standard adjustment sets. Any mediation-style use requires an explicitly different design.

## Randomized experimentation

Before treatment-effect reporting, run data-quality checks including assignment integrity and SRM. Treat unresolved SRM as a blocking trust issue.

Repeated peeking with fixed-horizon p-values is not allowed. Sequential monitoring must use an explicitly supported design.

## Observational inference

Do not claim “no unmeasured confounding” as a fact. Record it as an identifying assumption when required.

Overlap diagnostics are mandatory for propensity-based estimators. Unsupported extrapolation must be surfaced, not hidden.

## Panel / DiD

Do not use a naive staggered two-way-fixed-effects event study as the default when treatment timing and treatment effects are heterogeneous. Use explicit heterogeneity-robust estimators for staggered adoption.

## ML nuisance models

When flexible ML nuisance models are used for causal estimation, prefer orthogonal / doubly robust scores with sample splitting or cross-fitting where the task requires valid inference.

## Numerical integrity

LLMs must not generate treatment effects, confidence intervals, p-values, MDEs, propensity scores, or simulation results. Numerical results come from deterministic Python code.

## Reporting

Every final causal result includes:

- estimand,
- estimate,
- uncertainty,
- sample / population,
- estimator,
- key assumptions,
- diagnostics,
- sensitivity / robustness summary,
- limitations.

A failed diagnostic may change the report conclusion to “not identified / unreliable”; it must never be silently omitted.

## Reproducibility

Track where applicable:

- dataset version,
- analysis population,
- treatment/outcome definitions,
- DAG / adjustment set version,
- estimator and nuisance learners,
- formula / hyperparameters,
- seed,
- confidence level,
- trimming / overlap policy,
- analysis-run id,
- code version.

## Testing

Use synthetic known-effect data extensively. Test estimator bias, coverage, failure modes, overlap degradation, SRM, pre-trend violations, and reproducibility.

Do not weaken a correct test merely to make implementation pass.

## Dependencies

Prefer transparent implementations first. Heavy causal libraries require clear task-level justification and must be wrapped behind project interfaces.

## Documentation

Repository documentation and code comments are in English.

## Completion rule

Never mark a task complete unless implementation exists, required tests pass, its DoD is satisfied, and documentation is synchronized.
