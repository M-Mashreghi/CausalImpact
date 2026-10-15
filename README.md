# CausalImpact — Causal Inference & Experimentation Platform

CausalImpact is a research-oriented platform for designing, estimating, diagnosing, and reporting causal analyses. It is built around an **estimand-first, assumption-aware workflow** rather than a collection of black-box estimators.

## What the project demonstrates

- trustworthy A/B experimentation,
- observational causal inference,
- propensity-score and doubly robust methods,
- cross-fitted / double machine learning,
- Difference-in-Differences and event studies,
- modern staggered-adoption treatment-effect estimation,
- synthetic-control workflows,
- sensitivity and robustness analysis,
- heterogeneous treatment effects,
- policy / targeting evaluation,
- simulation-based validation,
- reproducible API/dashboard workflows.

## Core workflow

```text
Research Question
      ↓
Study Design + Causal DAG
      ↓
Treatment / Outcome / Target Population
      ↓
Estimand
      ↓
Identification Assumptions
      ↓
Estimator
      ↓
Diagnostics
      ↓
Sensitivity / Robustness
      ↓
Heterogeneity / Policy Value
      ↓
Assumption-Aware Report
```

## Important principle

A statistically significant coefficient is **not automatically a causal effect**. CausalImpact keeps design, identification, estimation, diagnostics, and reporting as separate layers.

## v1 method families

### Randomized experiments
- assignment integrity and SRM,
- baseline balance,
- difference in means / proportions,
- regression adjustment,
- CUPED-style variance reduction,
- power / MDE,
- guardrail metrics and multiple testing,
- clustered / stratified experiments,
- attrition and missing-outcome diagnostics,
- ratio / heavy-tailed metric support,
- sequential-monitoring guardrails.

### Observational inference
- causal DAG / adjustment-set planning,
- propensity scores,
- matching,
- IPW / overlap weights,
- outcome regression,
- AIPW,
- cross-fitting / Double ML,
- balance and overlap diagnostics.

### Panel / policy evaluation
- two-period and multi-period DiD,
- event studies,
- pre-trend diagnostics,
- cluster-robust inference,
- group-time ATT for staggered adoption,
- heterogeneity-robust event studies,
- synthetic control,
- placebo / falsification checks.

### Heterogeneity / decision support
- pre-specified subgroup effects,
- CATE baselines,
- honest tree / forest methods,
- policy-value evaluation.

## Intentionally post-v1

To keep the project finishable, these are documented but not mandatory in the main build:

- instrumental variables beyond randomized noncompliance examples,
- regression discontinuity,
- mediation,
- causal discovery,
- network interference,
- longitudinal g-methods,
- dynamic treatment regimes,
- Bayesian causal inference.

## Recommended stack

- Python 3.12+
- pandas / polars
- numpy / scipy
- statsmodels
- scikit-learn
- optional approved extensions: econml, dowhy, doubleml
- FastAPI
- Streamlit
- SQLite
- Parquet / DuckDB
- pytest
- Docker
- GitHub Actions

## Try it locally

See [docs/QUICKSTART.md](docs/QUICKSTART.md): install with `uv sync --extra dev`, run the
tests, the demo analyses, the dashboard, the study designer and the API.

## Start with Claude Code

```text
Read CLAUDE.md and all project governance documents.

Inspect Task 1.1 in:
docs/PROJECT_PHASES_AND_TASKS.md

Implement only Task 1.1.
Follow its Definition of Done.
Run required tests.
Update TASKS.md and PROJECT_PHASES_AND_TASKS.md only after verification succeeds.
Do not start Task 1.2.
```
