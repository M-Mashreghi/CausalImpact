# CausalImpact — Task Progress Ledger
Status: `[ ]` Pending · `[-]` In Progress · `[x]` Completed

## Phase 1 — Foundation, Causal Design & Reproducibility
- [x] **Task 1.1** — Python Project Scaffold & Quality Tooling (`Core`)
- [x] **Task 1.2** — Canonical StudyDesign & AnalysisRun Domain Models (`Core`)
- [x] **Task 1.3** — Treatment, Outcome & Covariate Data Contracts (`Core`)
- [x] **Task 1.4** — Estimand Registry (`Core`)
- [x] **Task 1.5** — Causal DAG & Adjustment-Set Registry (`Core`)
- [x] **Task 1.6** — Assumption Registry & Design Validation (`Core`)
- [x] **Task 1.7** — Dataset Versioning, Seeds & Reproducible Run Identity (`Core`)

## Phase 2 — Randomized Experiments & Product Experimentation
- [x] **Task 2.1** — Experiment Assignment & Logging Integrity (`Core`)
- [x] **Task 2.2** — Sample Ratio Mismatch Detection & Triage (`Core`)
- [x] **Task 2.3** — Baseline Balance Diagnostics (`Core`)
- [x] **Task 2.4** — Difference-in-Means & Difference-in-Proportions (`Core`)
- [x] **Task 2.5** — Regression-Adjusted Experiment Estimator (`Core`)
- [x] **Task 2.6** — CUPED / Pre-Period Variance Reduction (`Core`)
- [x] **Task 2.7** — Power, MDE & Sample Size Engine (`Core`)
- [x] **Task 2.8** — Guardrail Metrics & Multiple-Testing Policy (`Core`)
- [ ] **Task 2.9** — Clustered / Stratified Experiment Inference (`Advanced`)
- [x] **Task 2.10** — Attrition & Missing-Outcome Diagnostics (`Core`)
- [ ] **Task 2.11** — Ratio & Heavy-Tailed Metric Analysis (`Advanced`)
- [ ] **Task 2.12** — Sequential Monitoring / Peeking Guardrails (`Advanced`)

## Phase 3 — Observational Causal Inference & Double ML
- [x] **Task 3.1** — Observational Covariate Temporal Eligibility (`Core`)
- [x] **Task 3.2** — Propensity Score Estimation (`Core`)
- [x] **Task 3.3** — Overlap / Positivity Diagnostics (`Core`)
- [x] **Task 3.4** — Matching Engine & Matched-Sample Diagnostics (`Core`)
- [x] **Task 3.5** — IPW / Stabilized / Overlap Weighting (`Core`)
- [x] **Task 3.6** — Outcome Regression Adjustment (`Core`)
- [x] **Task 3.7** — Doubly Robust AIPW Estimator (`Core`)
- [ ] **Task 3.8** — Cross-Fitting & Double ML Engine (`Advanced`)
- [x] **Task 3.9** — Covariate Balance & Weighted Diagnostics (`Core`)
- [ ] **Task 3.10** — Observational Falsification / Negative-Control Hooks (`Advanced`)

## Phase 4 — Difference-in-Differences & Policy Evaluation
- [x] **Task 4.1** — Panel Data Contract & Treatment Timing Model (`Core`)
- [x] **Task 4.2** — Two-Period Difference-in-Differences (`Core`)
- [x] **Task 4.3** — Multi-Period DiD Baseline (`Core`)
- [x] **Task 4.4** — Classical Event-Study Diagnostic (`Core`)
- [x] **Task 4.5** — Pre-Trend Diagnostics (`Core`)
- [x] **Task 4.6** — Cluster-Robust Inference (`Core`)
- [ ] **Task 4.7** — Group-Time ATT for Staggered Adoption (`Advanced`)
- [ ] **Task 4.8** — Heterogeneity-Robust Dynamic Event Study (`Advanced`)
- [ ] **Task 4.9** — Synthetic Control & Donor-Pool Diagnostics (`Advanced`)
- [ ] **Task 4.10** — Placebo / Falsification Tests (`Advanced`)

## Phase 5 — Sensitivity, Heterogeneity & Policy Value
- [x] **Task 5.1** — Specification Robustness Runner (`Core`)
- [ ] **Task 5.2** — Unmeasured-Confounding Sensitivity Interface (`Advanced`)
- [x] **Task 5.3** — Weight Trimming / Overlap Sensitivity (`Core`)
- [x] **Task 5.4** — Pre-Specified Subgroup Effects (`Core`)
- [x] **Task 5.5** — Exploratory Heterogeneity Guardrails (`Core`)
- [ ] **Task 5.6** — CATE Baseline (`Advanced`)
- [ ] **Task 5.7** — Honest Tree / Forest Heterogeneity (`Advanced`)
- [ ] **Task 5.8** — Policy / Targeting Value Evaluation (`Advanced`)

## Phase 6 — API, Dashboard & Reproducible Workflow
- [x] **Task 6.1** — Core Causal Analysis Service (`Core`)
- [x] **Task 6.2** — FastAPI Study & Analysis API (`Core`)
- [x] **Task 6.3** — Streamlit Study Designer (`Core`)
- [x] **Task 6.4** — Diagnostics Dashboard (`Core`)
- [x] **Task 6.5** — Estimator / Specification Comparison (`Core`)
- [x] **Task 6.6** — Assumption-Aware Report Generator (`Core`)
- [x] **Task 6.7** — Analysis Registry, Re-Run & Reproducibility Bundle (`Core`)

## Phase 7 — Simulation Benchmarking & Research Validation
- [x] **Task 7.1** — Synthetic Data Generator with Known Effects (`Core`)
- [x] **Task 7.2** — Estimator Bias / RMSE Benchmark Harness (`Core`)
- [x] **Task 7.3** — Confidence Interval Coverage Benchmark (`Core`)
- [x] **Task 7.4** — Poor-Overlap & Extreme-Weight Stress Tests (`Core`)
- [ ] **Task 7.5** — Nuisance Misspecification & Cross-Fitting Tests (`Advanced`)
- [x] **Task 7.6** — DiD / Experiment Failure-Mode Simulation Suite (`Core`)

## Phase 8 — Hardening, CI/CD & Operations
- [ ] **Task 8.1** — End-to-End Regression Suite (`Core`)
- [ ] **Task 8.2** — Observability & Health Checks (`Core`)
- [ ] **Task 8.3** — Dockerization & Demo Stack (`Core`)
- [ ] **Task 8.4** — GitHub Actions CI & Research Gates (`Core`)
- [ ] **Task 8.5** — Operational Runbook, Security & Release Checklist (`Core`)
