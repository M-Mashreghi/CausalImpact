# CausalImpact Roadmap

## Vision

A transparent causal-research workbench that supports trustworthy experimentation and observational causal analysis while making assumptions, diagnostics, and uncertainty first-class artifacts.

## M1 — Design & reproducibility
Study domain, data contracts, DAGs, estimands, assumptions, immutable analysis runs.

## M2 — Trustworthy experimentation
SRM, balance, effect estimators, CUPED, power/MDE, guardrails, clustered designs, missingness, robust product metrics, monitoring safeguards.

## M3 — Observational causal inference
Propensity methods, matching/weighting, AIPW, overlap diagnostics, cross-fitting / DML.

## M4 — Policy / panel inference
DiD, event studies, staggered-adoption robust estimators, synthetic control, placebos.

## M5 — Robustness & heterogeneity
Sensitivity, specification curves, CATE, honest heterogeneity methods, policy value.

## M6 — Product workflow
API, study designer, diagnostics dashboard, reproducibility bundles, reports.

## M7 — Validation
Simulation benchmark suite for bias, coverage, overlap, staggered DiD, and experiment failure modes.

## M8 — Production hardening
Docker, CI, health, security, runbook.

## Acceptance KPIs

| KPI | Target |
|---|---:|
| Mandatory test suite | 100% pass |
| Known-effect estimator benchmarks | required |
| Silent post-treatment adjustment | 0 |
| Silent estimand switch | 0 |
| Unresolved SRM labeled trustworthy | 0 |
| Reports without uncertainty | 0 |
| Reproducible saved runs | 100% on fixtures |
