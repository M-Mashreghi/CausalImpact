# CausalImpact — Project Phases & Atomic Tasks
**Single source of truth** for implementation scope and completion.
Legend: `[ ]` Not Started · `[-]` In Progress · `[x]` Completed
## Global Definition of Done
Every task must satisfy:

1. Task-specific tests pass.
2. Causal assumptions and estimand remain explicit.
3. No silent post-treatment adjustment or population change.
4. Numerical results are reproducible.
5. Relevant docs/ledgers are synchronized.
6. No unrelated refactors.
7. New dependencies are justified.

---

## Phase 1 — Foundation, Causal Design & Reproducibility

### Task 1.1: Python Project Scaffold & Quality Tooling

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Python Project Scaffold & Quality Tooling` without weakening design/identification boundaries.

**Technical specification**
- Create package layout, pyproject, lint/type/test configuration.
- Pin a supported Python baseline and deterministic test environment.

**Task-specific verification**
- [x] Fresh install imports package.
- [x] pytest smoke suite passes.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `pyproject.toml` (hatchling, `requires-python >=3.12,<3.14`), `.python-version` (3.12), `uv.lock`, `src/causalimpact/` with the 18 subpackages from `PROJECT_STRUCTURE.md`, `py.typed`.
- Tooling: pytest (strict markers/config, warnings as errors, `integration`/`simulation`/`e2e` markers), ruff lint+format, mypy strict with pydantic plugin.
- Determinism: tests use the seeded `rng` fixture in `tests/conftest.py`, never global RNG state; dependency versions locked in `uv.lock`.
- Dependencies: numpy, pandas, scipy, pydantic only (pydantic for typed domain contracts in Task 1.2+); others are deferred to the task that needs them.
- Tests: `tests/unit/test_smoke.py` (21 passed).
- Verification: wheel built and imported in a clean Python 3.12 venv; `pytest`, `ruff check`, `ruff format --check`, `mypy` all clean.
- Assumption/estimand changes: none.

---

### Task 1.2: Canonical StudyDesign & AnalysisRun Domain Models

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Canonical StudyDesign & AnalysisRun Domain Models` without weakening design/identification boundaries.

**Technical specification**
- Define immutable ids, statuses, design family, population and run metadata.
- Separate StudyDesign from AnalysisRun so the same design can support multiple specifications.

**Task-specific verification**
- [x] Valid lifecycle transitions pass.
- [x] Illegal/missing core fields fail.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/domain/` — `ids.py` (prefixed, validated `design_`/`run_` ids), `study_design.py` (`StudyDesign`, `TargetPopulation`, `DesignFamily`, `DesignStatus`, transition table), `analysis_run.py` (`AnalysisRun`, `RunStatus`), `errors.py`.
- Models are frozen pydantic models; transitions and revisions return new objects and append a `StatusChange` history. Revisions are only allowed in Draft and bump `version` while keeping `design_id`.
- Lifecycle: Draft → Validated → AnalysisReady → Estimated → Reviewed → Reported, plus Validated/AnalysisReady → Draft for revision. Promotion to AnalysisReady requires a readiness check and the default check refuses (fail closed); the structured check arrives in Task 1.6.
- AnalysisRun is separate from StudyDesign: `AnalysisRun.for_design` requires an analyzable design, pins `design_id` + `design_version`, and refuses a run whose estimand, DAG version or adjustment-set version differs from the design (no silent estimand switch). Runs are invalidated with a reason, never overwritten.
- Tests: `tests/unit/domain/test_study_design.py`, `tests/unit/domain/test_analysis_run.py` (exhaustive illegal-transition matrices, missing/blank core fields, immutability, JSON round-trip). Suite: 117 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 1.3: Treatment, Outcome & Covariate Data Contracts

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Treatment, Outcome & Covariate Data Contracts` without weakening design/identification boundaries.

**Technical specification**
- Implement treatment/outcome schemas and covariate temporal metadata.
- Block automatic adjustment for variables with unknown timing or known treatment descendants.

**Task-specific verification**
- [x] Temporal-safety fixtures pass.
- [x] Schema rejects malformed outcomes/treatments.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/domain/variables.py` (`TreatmentSpec`, `OutcomeSpec`, `CovariateSpec` with `TriState` temporal metadata, `DataContract`, `classify_covariate`), `src/causalimpact/validation/schema.py` (`validate_frame`, `ensure_valid`, `ValidationReport`).
- Temporal safety: known treatment descendants and post-treatment variables are `forbidden`; unknown timing or unknown descendant status is `review_required`; only known pre-treatment, non-descendant covariates are returned by `automatic_adjustment_candidates()`. Contradictory metadata (pre-treatment and descendant) and pre-treatment without a measurement time are rejected.
- Schema validation errors: missing columns, missing/duplicate unit ids, missing or out-of-contract treatment values, single arm, non-numeric/boolean/infinite outcomes, non-0/1 binary and invalid count outcomes, covariate dtype and forbidden missingness, invalid weights, missing cluster/stratum labels, non-datetime timestamps. Missing outcomes are a visible warning (attrition handled by Task 2.10), never dropped.
- Tests: `tests/unit/domain/test_variables.py` (all 8 legal temporal combinations), `tests/unit/validation/test_schema.py`. Suite: 161 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none. Metadata eligibility is necessary, not sufficient; DAG checks follow in Tasks 1.5 and 3.1.

---

### Task 1.4: Estimand Registry

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Estimand Registry` without weakening design/identification boundaries.

**Technical specification**
- Represent ATE, ATT, ATC, CATE and ITT with target-population metadata.
- Require estimator outputs to declare the estimand they target.

**Task-specific verification**
- [x] Estimand serialization round-trips.
- [x] Mismatched estimand/output contract fails.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/domain/estimands.py` (`Estimand`, `EstimandType` ATE/ATT/ATC/CATE/ITT, `TreatmentBasis`, `EffectScale`, `EffectEstimate`, `EstimandRegistry`, `check_estimate_targets`), `src/causalimpact/estimators/base.py` (`Estimator` protocol, `run_estimator`).
- Every estimand carries treatment, outcome, `TargetPopulation`, treatment basis and scale. Rules: CATE requires conditioning variables (never treatment/outcome), other types reject them; ITT must be defined on assignment.
- Estimator outputs (`EffectEstimate`) must declare `estimand_id` and `estimand_type` and are numerically sane (finite, SE ≥ 0, estimate inside CI). `run_estimator` refuses unsupported estimand types before fitting and rejects outputs that declare a different estimand, estimator or confidence level.
- Registry is immutable per id: identical re-registration is a no-op, redefinition is refused; JSON round-trip is byte-stable.
- Tests: `tests/unit/domain/test_estimands.py`. Suite: 198 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 1.5: Causal DAG & Adjustment-Set Registry

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Causal DAG & Adjustment-Set Registry` without weakening design/identification boundaries.

**Technical specification**
- Store DAG nodes/edges and versioned proposed adjustment sets.
- Implement guardrails for mediators, descendants and declared colliders.

**Task-specific verification**
- [x] Known backdoor examples yield expected safe/unsafe flags.
- [x] Versioning is reproducible.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/dags/graph.py` (`CausalDAG`, `DagNode`, `AdjustmentSet`, `assess_adjustment_set`, `AdjustmentAssessment`, `VariableFlag`), `src/causalimpact/dags/registry.py` (`DagRegistry`). No graph library dependency: transparent BFS/moral-graph code.
- DAGs validate acyclicity, declared nodes, no self-loops/duplicates, and nodes may be marked unobserved. Versions are content hashes (`dag_…`, `adjset_…`) independent of declaration order; an adjustment set is bound to the exact DAG version it was built for.
- Guardrails: per-variable flags for mediator, descendant of treatment, declared collider, unobserved, not in DAG, and treatment/outcome. The backdoor criterion is checked exactly (no descendants + d-separation in the backdoor graph via the moralised ancestral graph), so collider adjustment that opens a path (M-bias) fails even without a declaration. Open backdoor paths are enumerated for explanation; every assessment carries the caveat that the DAG itself is an untestable assumption.
- Tests: `tests/unit/dags/test_dag.py` — confounder, mediator, non-mediator descendant, M-bias (with/without blocking), declared collider, latent confounder, Pearl backdoor example (7 sets), path-enumeration/d-separation agreement, versioning and registry round-trip. Suite: 228 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 1.6: Assumption Registry & Design Validation

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Assumption Registry & Design Validation` without weakening design/identification boundaries.

**Technical specification**
- Define structured assumptions by design family.
- Implement AnalysisReady validation that fails closed for missing identification fields.

**Task-specific verification**
- [x] Incomplete design cannot become AnalysisReady.
- [x] Assumptions survive serialization.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/domain/assumptions.py` (`Assumption`, `Testability`, `AssumptionStatus`), `src/causalimpact/design/assumption_catalog.py` (required assumptions per design family from CAUSAL_ASSUMPTIONS.md), `src/causalimpact/design/readiness.py` (`DesignReadinessValidator`), `src/causalimpact/domain/types.py` (shared constrained types, split out to avoid a domain import cycle). `StudyDesign` gains `assumptions` and `randomization_unit`.
- Assumption status has no "proven" value: only assumed / diagnostic support / diagnostic concern / violated. Conditional exchangeability and parallel trends are catalogued as untestable.
- `DesignReadinessValidator` is the `ReadinessCheck` for AnalysisReady and reports every blocking problem at once: missing common and family-specific fields, undeclared/unjustified/violated required assumptions, unregistered or mismatched estimand (treatment, outcome, population; ITT only for randomized designs), unregistered DAG/adjustment set, unsafe adjustment variables, backdoor failure, forbidden post-treatment variables in the set, and randomization unit ≠ analysis unit without a cluster variable.
- Tests: `tests/unit/design/test_readiness.py` (complete RCT/observational/panel designs promote; every required field, every required assumption and each reference failure blocks; assumptions survive JSON round-trip). Suite: 267 passed; ruff and mypy strict clean.
- Assumption/estimand changes: assumptions are now explicit per family (documented above); no estimand change.

---

### Task 1.7: Dataset Versioning, Seeds & Reproducible Run Identity

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Dataset Versioning, Seeds & Reproducible Run Identity` without weakening design/identification boundaries.

**Technical specification**
- Hash/version analysis datasets and configs.
- Derive stable run identity from dataset/design/config where appropriate.

**Task-specific verification**
- [x] Same inputs reproduce id/result seeds.
- [x] Changed config changes run fingerprint.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/domain/fingerprint.py` (`canonical_json`, `content_hash`, `derive_seed`), `src/causalimpact/ingestion/dataset_version.py` (`dataset_version`, `DatasetVersion`), `StudyDesign.content_hash`, and on `AnalysisRun` the new required `design_content_hash` plus `fingerprint` and `derived_seed(purpose)`.
- Dataset hash: SHA-256 over row count, column names, dtypes and pandas value hashes. Column order and index are ignored; row order is kept because seeded steps depend on it. Verified stable across processes.
- Run identity: `run_id` identifies an execution; `fingerprint` identifies the specification (design content, dataset version, estimand, estimator, DAG/adjustment set, learners, config, seed, confidence level, code version) and excludes lifecycle fields. Design content hash excludes id, version, status, history and timestamp.
- Seeds: `derive_seed(root, purpose)` depends only on the root seed and purpose label, so adding a random step does not shift existing streams.
- Tests: `tests/unit/test_reproducibility.py` (same inputs → same hash/fingerprint/seeds; each config, data, design or code-version change → new fingerprint; lifecycle and JSON round-trip keep the fingerprint). Suite: 295 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

## Phase 2 — Randomized Experiments & Product Experimentation

### Task 2.1: Experiment Assignment & Logging Integrity

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Experiment Assignment & Logging Integrity` without weakening design/identification boundaries.

**Technical specification**
- Validate randomization unit, assignment, exposure and analysis-unit consistency.
- Detect duplicates/cross-arm contamination where possible.

**Task-specific verification**
- [x] Clean fixture passes.
- [x] Corrupted assignment/exposure fixtures fail.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/spec.py` (`ExperimentSpec`, `Arm`, `MonitoringPolicy` — experiment metadata from DATA_CONTRACT.md with separate randomization/analysis unit columns), `src/causalimpact/experiments/integrity.py` (`check_assignment_integrity`), `src/causalimpact/diagnostics/base.py` (shared `DiagnosticResult` / `Finding` with pass / warning / blocking status, reused by later diagnostics).
- Blocking findings: missing columns, missing assignment fields, unknown arms, units assigned to more than one arm, exposure without assignment, cross-arm exposure, exposure before assignment, duplicate analysis units, analysis units mapped to several randomization units, analysis rows without a valid assignment, analysis arm ≠ assigned arm (ITT analyses units as assigned).
- Warnings (visible, not dropped): duplicate assignment log rows with the same arm; assigned units missing from analysis (handed to attrition diagnostics, Task 2.10). A note requires clustered inference when the analysis unit is finer than the randomization unit. Nothing is repaired or filtered.
- Tests: `tests/unit/experiments/test_integrity.py` (clean user-level and household-cluster fixtures pass; 9 corrupted fixtures each block with the expected code). Suite: 315 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 2.2: Sample Ratio Mismatch Detection & Triage

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Sample Ratio Mismatch Detection & Triage` without weakening design/identification boundaries.

**Technical specification**
- Implement chi-square SRM detection against configured allocation.
- Return blocking trust status plus diagnostic metadata.

**Task-specific verification**
- [x] Known balanced/unbalanced fixtures classify correctly.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/srm.py` (`check_srm`, `check_srm_from_assignments`, `DEFAULT_SRM_ALPHA = 0.001`).
- Pearson chi-square goodness-of-fit against the configured allocation; exact binomial test for two arms with any expected count < 5; with more arms and small expected counts the result carries an `srm_test_unreliable` warning. Arms absent from the counts count as zero; unknown arms and negative counts are rejected.
- A detected SRM is a blocking finding naming the arm with the largest share deviation, plus a triage checklist note (RUNBOOK.md). Metrics: method, statistic, df, p-value, observed/expected counts, configured vs observed allocation.
- Tests: `tests/unit/experiments/test_srm.py` (balanced/unbalanced 2-arm, unequal allocation, 3-arm, exact path, chi-square p-value checked against the independent closed form erfc(√(x/2)); simulations: false-positive rate ≈ α under correct allocation, detection of a 5% one-arm logging loss at 100k units). Suite: 331 passed; ruff and mypy strict clean (mypy ignores missing scipy stubs; documented in pyproject).
- Assumption/estimand changes: none.

---

### Task 2.3: Baseline Balance Diagnostics

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Baseline Balance Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compute standardized differences and descriptive balance by arm.
- Do not use balance p-values as a randomization-validity gate.

**Task-specific verification**
- [x] Hand-computed balance fixture matches.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/diagnostics/balance.py` (`standardized_mean_difference`, `balance_table`, `BalanceRow`, `summarize_balance` — shared with weighted balance in Task 3.9), `src/causalimpact/experiments/balance.py` (`check_baseline_balance`).
- SMD with pooled SD sqrt((s²_t + s²_c)/2): sample variances (ddof=1) for numeric covariates, p(1−p) for binary covariates and categorical-level indicators. Each non-control arm is compared with control. Missing values are counted per arm, never imputed. Undefined SMDs (empty arm, zero variance with different means) are reported, not hidden.
- No balance p-values anywhere. |SMD| > 0.1 is a descriptive warning recommending pre-specified adjustment, never a blocking validity gate. Only covariates known to be pre-treatment and not affected by treatment are accepted.
- Tests: `tests/unit/experiments/test_balance.py` (hand-computed numeric −1.0392, binary 0.6626 and categorical-level SMDs; missing handling; post-treatment refusal; multi-arm; large randomized simulation max |SMD| < 0.05). Suite: 340 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 2.4: Difference-in-Means & Difference-in-Proportions

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Difference-in-Means & Difference-in-Proportions` without weakening design/identification boundaries.

**Technical specification**
- Implement basic ITT estimators for continuous and binary outcomes.
- Return estimate, SE/CI and sample counts.

**Task-specific verification**
- [x] Known-effect simulation is approximately unbiased.
- [x] Null fixture CI behavior is sensible.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/estimators.py` (`DifferenceInMeans`, `DifferenceInProportions`, `split_arms`), both implementing the `Estimator` protocol. `EffectEstimate` gains optional `p_value` and `degrees_of_freedom`.
- Both target ITT only (units analysed as assigned) and refuse ATE. Difference in means: Neyman variance with Welch–Satterthwaite t interval. Difference in proportions: unpooled Wald variance with normal interval; degenerate 0/1-only arms are refused rather than reported with a zero-width CI.
- Missing outcomes, unknown arm labels, arms with < 2 units and a treatment column that differs from the estimand are refused; nothing is dropped silently.
- Tests: `tests/unit/experiments/test_estimators.py` (hand-computed Welch fixture agreeing with `scipy.stats.ttest_ind(equal_var=False)`; hand-computed Wald fixture; refusals; simulations: bias within 4 Monte Carlo SEs for three known effects, null 95% CI coverage in [0.93, 0.97] for both estimators). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none (ITT only).

---

### Task 2.5: Regression-Adjusted Experiment Estimator

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Regression-Adjusted Experiment Estimator` without weakening design/identification boundaries.

**Technical specification**
- Implement covariate-adjusted experiment estimator using pre-treatment covariates.
- Preserve ITT interpretation and robust uncertainty.

**Task-specific verification**
- [x] Adjustment improves precision on prognostic fixture without biasing truth.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/estimators/ols.py` (`ols_hc2`: transparent OLS with HC2 covariance), `src/causalimpact/experiments/regression.py` (`RegressionAdjustedITT`, `covariate_matrix`).
- Lin (2013) estimator: outcome on assignment, mean-centred pre-treatment covariates and assignment × covariate interactions; categoricals one-hot encoded; missing covariates only under the `indicator` policy. Targets ITT only; post-treatment / review-required covariates and the outcome itself are refused; rank-deficient designs raise.
- Variance targets the population ITT: HC2 variance of the assignment coefficient plus g′S_xg/n for estimating the centring means. Found during verification: HC2 alone under-covered (0.875) with heterogeneous effects; after the fix coverage was 0.93–0.97 across seeds.
- Tests: `tests/unit/experiments/test_regression.py` (HC2 without covariates equals the Neyman variance; coefficient equals direct least squares; SE < half of unadjusted on a prognostic fixture; refusals; simulations with homogeneous and heterogeneous effects: unbiased, coverage in [0.92, 0.98], variance < 25% of difference in means). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none (ITT preserved).

---

### Task 2.6: CUPED / Pre-Period Variance Reduction

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `CUPED / Pre-Period Variance Reduction` without weakening design/identification boundaries.

**Technical specification**
- Implement CUPED-style residualization from pre-treatment metric.
- Verify covariate is temporally prior and not treatment affected.

**Task-specific verification**
- [ ] Known correlated pre-period fixture reduces variance.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.7: Power, MDE & Sample Size Engine

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Power, MDE & Sample Size Engine` without weakening design/identification boundaries.

**Technical specification**
- Implement power/MDE for supported metric types and allocation ratios.
- Keep planning calculations separate from post-hoc inference.

**Task-specific verification**
- [ ] Reference examples match tolerance.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.8: Guardrail Metrics & Multiple-Testing Policy

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Guardrail Metrics & Multiple-Testing Policy` without weakening design/identification boundaries.

**Technical specification**
- Support primary/secondary/guardrail metric roles.
- Implement approved multiplicity corrections and decision metadata.

**Task-specific verification**
- [ ] Correction methods match reference fixtures.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.9: Clustered / Stratified Experiment Inference

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Clustered / Stratified Experiment Inference` without weakening design/identification boundaries.

**Technical specification**
- Represent cluster/stratum randomization.
- Implement appropriate clustered or stratification-aware uncertainty for supported cases.

**Task-specific verification**
- [ ] Cluster simulation does not use naive iid SEs.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.10: Attrition & Missing-Outcome Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Attrition & Missing-Outcome Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compare missingness/attrition by arm and over time.
- Block clean ship/no-ship labels when differential attrition is unresolved.

**Task-specific verification**
- [ ] Differential attrition fixture triggers warning/block.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.11: Ratio & Heavy-Tailed Metric Analysis

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Ratio & Heavy-Tailed Metric Analysis` without weakening design/identification boundaries.

**Technical specification**
- Add safe analysis path for ratio/revenue-like metrics with documented variance method.
- Support robust/winsorized policy only when predeclared.

**Task-specific verification**
- [ ] Heavy-tail fixture remains numerically stable.
- [ ] Ratio estimator tests against simulated truth.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 2.12: Sequential Monitoring / Peeking Guardrails

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Sequential Monitoring / Peeking Guardrails` without weakening design/identification boundaries.

**Technical specification**
- Represent fixed-horizon vs sequential monitoring policy.
- Detect unsupported repeated-look usage and expose a separate sequential-analysis extension point.

**Task-specific verification**
- [ ] Fixed-horizon repeated-peek fixture is flagged.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 3 — Observational Causal Inference & Double ML

### Task 3.1: Observational Covariate Temporal Eligibility

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Observational Covariate Temporal Eligibility` without weakening design/identification boundaries.

**Technical specification**
- Validate proposed adjustment variables against DAG and timing metadata.
- Produce allowed, forbidden and review-required covariate sets.

**Task-specific verification**
- [ ] Mediator/collider/post-treatment fixtures flagged.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.2: Propensity Score Estimation

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Propensity Score Estimation` without weakening design/identification boundaries.

**Technical specification**
- Implement baseline logistic propensity estimator behind interface.
- Persist predicted propensity and nuisance-model config.

**Task-specific verification**
- [ ] Probabilities bounded and reproducible.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.3: Overlap / Positivity Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Overlap / Positivity Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Plot/summarize treatment-specific propensity distributions.
- Compute overlap violations, support/effective sample diagnostics and refusal thresholds.

**Task-specific verification**
- [ ] Poor-overlap fixture flagged.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.4: Matching Engine & Matched-Sample Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Matching Engine & Matched-Sample Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Implement at least one transparent matching strategy.
- Report matched counts, distance quality and post-match balance.

**Task-specific verification**
- [ ] Known toy match pairs are reproducible.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.5: IPW / Stabilized / Overlap Weighting

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `IPW / Stabilized / Overlap Weighting` without weakening design/identification boundaries.

**Technical specification**
- Implement supported weighting schemes with explicit estimand mapping.
- Report weight distribution and effective sample size.

**Task-specific verification**
- [ ] Weights normalize as documented.
- [ ] Extreme-weight fixture surfaced.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.6: Outcome Regression Adjustment

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Outcome Regression Adjustment` without weakening design/identification boundaries.

**Technical specification**
- Implement regression-adjusted ATE/ATT baseline with explicit covariates.
- Keep nuisance prediction separate from causal effect object.

**Task-specific verification**
- [ ] Known linear DGP recovers truth.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.7: Doubly Robust AIPW Estimator

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Doubly Robust AIPW Estimator` without weakening design/identification boundaries.

**Technical specification**
- Implement AIPW with outcome and propensity nuisance models.
- Expose influence-function based uncertainty for supported iid case.

**Task-specific verification**
- [ ] One correctly specified nuisance path remains approximately unbiased in simulation.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.8: Cross-Fitting & Double ML Engine

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Cross-Fitting & Double ML Engine` without weakening design/identification boundaries.

**Technical specification**
- Implement fold-aware nuisance training/prediction without self-prediction leakage.
- Support orthogonal-score causal estimation for approved models.

**Task-specific verification**
- [ ] Every unit receives out-of-fold nuisance predictions.
- [ ] Fixed seed reproduces folds/result.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.9: Covariate Balance & Weighted Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Covariate Balance & Weighted Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compute SMD before/after matching/weighting.
- Create Love-plot-ready data and balance thresholds.

**Task-specific verification**
- [ ] Hand-computed SMD fixtures match.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 3.10: Observational Falsification / Negative-Control Hooks

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Observational Falsification / Negative-Control Hooks` without weakening design/identification boundaries.

**Technical specification**
- Provide contracts for negative-control outcome/exposure or placebo checks.
- Report as falsification evidence, not proof of identification.

**Task-specific verification**
- [ ] Placebo fixture surfaces expected null/non-null behavior.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 4 — Difference-in-Differences & Policy Evaluation

### Task 4.1: Panel Data Contract & Treatment Timing Model

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Panel Data Contract & Treatment Timing Model` without weakening design/identification boundaries.

**Technical specification**
- Define unit-period schema, treatment start, never-treated/not-yet-treated flags.
- Validate treatment timing consistency.

**Task-specific verification**
- [ ] Malformed timing fixtures fail.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.2: Two-Period Difference-in-Differences

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Two-Period Difference-in-Differences` without weakening design/identification boundaries.

**Technical specification**
- Implement transparent 2x2 DiD estimand with uncertainty.
- Return group-time descriptive components.

**Task-specific verification**
- [ ] Known-effect DGP recovered.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.3: Multi-Period DiD Baseline

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Multi-Period DiD Baseline` without weakening design/identification boundaries.

**Technical specification**
- Implement supported multi-period specification for non-staggered/controlled cases.
- Make comparison-group rules explicit.

**Task-specific verification**
- [ ] Balanced panel fixture matches reference.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.4: Classical Event-Study Diagnostic

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Classical Event-Study Diagnostic` without weakening design/identification boundaries.

**Technical specification**
- Produce relative-time coefficients for appropriate settings.
- Label as diagnostic/baseline and warn on staggered heterogeneous use.

**Task-specific verification**
- [ ] Relative-time indexing correct.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.5: Pre-Trend Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Pre-Trend Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compute pre-period coefficients/joint diagnostics and plots.
- Report inability to prove parallel trends.

**Task-specific verification**
- [ ] Injected pre-trend is detected in simulation.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.6: Cluster-Robust Inference

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Cluster-Robust Inference` without weakening design/identification boundaries.

**Technical specification**
- Support cluster-robust SE configuration for panel estimators.
- Validate cluster count and warn for unsupported small-cluster inference.

**Task-specific verification**
- [ ] Clustered DGP SE differs from naive iid as expected.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.7: Group-Time ATT for Staggered Adoption

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Group-Time ATT for Staggered Adoption` without weakening design/identification boundaries.

**Technical specification**
- Implement or wrap heterogeneity-robust group/time ATT estimator with explicit comparison cohorts.
- Aggregate to overall/dynamic effects transparently.

**Task-specific verification**
- [ ] Staggered heterogeneous DGP avoids known TWFE contamination pattern.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.8: Heterogeneity-Robust Dynamic Event Study

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Heterogeneity-Robust Dynamic Event Study` without weakening design/identification boundaries.

**Technical specification**
- Implement interaction-weighted or equivalent approved dynamic estimator.
- Keep cohort weights visible in artifacts.

**Task-specific verification**
- [ ] Synthetic staggered event-time truth recovered within tolerance.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.9: Synthetic Control & Donor-Pool Diagnostics

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Synthetic Control & Donor-Pool Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Implement single-treated-unit synthetic-control workflow.
- Report donor weights, pre-fit RMSE and donor-pool provenance.

**Task-specific verification**
- [ ] Known synthetic-control fixture reproduces pre-period fit.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 4.10: Placebo / Falsification Tests

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Placebo / Falsification Tests` without weakening design/identification boundaries.

**Technical specification**
- Implement in-space/in-time placebo hooks for policy workflows.
- Report placebo distribution without overclaiming significance.

**Task-specific verification**
- [ ] Null/treated synthetic fixtures produce expected rank behavior.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 5 — Sensitivity, Heterogeneity & Policy Value

### Task 5.1: Specification Robustness Runner

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Specification Robustness Runner` without weakening design/identification boundaries.

**Technical specification**
- Run approved alternative covariate/specification grids without hidden researcher degrees of freedom.
- Store every attempted spec, not only favorable ones.

**Task-specific verification**
- [ ] All configured specs appear in output.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.2: Unmeasured-Confounding Sensitivity Interface

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Unmeasured-Confounding Sensitivity Interface` without weakening design/identification boundaries.

**Technical specification**
- Implement at least one transparent sensitivity method or framework.
- Report sensitivity assumptions/scale alongside main effect.

**Task-specific verification**
- [ ] Sensitivity parameter sweep reproducible.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.3: Weight Trimming / Overlap Sensitivity

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Weight Trimming / Overlap Sensitivity` without weakening design/identification boundaries.

**Technical specification**
- Re-estimate across predeclared trimming/overlap policies.
- Track estimand/population changes caused by restriction.

**Task-specific verification**
- [ ] Restricted sample/estimand metadata updates correctly.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.4: Pre-Specified Subgroup Effects

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Pre-Specified Subgroup Effects` without weakening design/identification boundaries.

**Technical specification**
- Estimate subgroup effects only for declared groups using shared estimand.
- Report multiplicity/uncertainty.

**Task-specific verification**
- [ ] Subgroup definitions are versioned and reproducible.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.5: Exploratory Heterogeneity Guardrails

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Exploratory Heterogeneity Guardrails` without weakening design/identification boundaries.

**Technical specification**
- Separate exploratory findings from confirmatory results.
- Require holdout/cross-fitting or honest labeling of exploratory status.

**Task-specific verification**
- [ ] Report labels exploratory results correctly.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.6: CATE Baseline

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `CATE Baseline` without weakening design/identification boundaries.

**Technical specification**
- Implement simple CATE learner with cross-fitting where required.
- Return individual predictions plus population calibration summaries.

**Task-specific verification**
- [ ] Known heterogeneous DGP shows directional recovery.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.7: Honest Tree / Forest Heterogeneity

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Honest Tree / Forest Heterogeneity` without weakening design/identification boundaries.

**Technical specification**
- Add honest/sample-split treatment-effect tree/forest path.
- Prevent training/evaluation reuse in heterogeneity claims.

**Task-specific verification**
- [ ] Honest split is enforced.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 5.8: Policy / Targeting Value Evaluation

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Policy / Targeting Value Evaluation` without weakening design/identification boundaries.

**Technical specification**
- Evaluate treatment policy against treat-all/treat-none baselines on held-out data.
- Include cost/benefit configuration where provided.

**Task-specific verification**
- [ ] Known policy DGP yields expected value ordering.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 6 — API, Dashboard & Reproducible Workflow

### Task 6.1: Core Causal Analysis Service

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Core Causal Analysis Service` without weakening design/identification boundaries.

**Technical specification**
- Orchestrate design validation → estimator → diagnostics → report artifacts.
- Fail closed when required diagnostics block interpretation.

**Task-specific verification**
- [ ] Happy path and blocked path integration tests.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.2: FastAPI Study & Analysis API

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `FastAPI Study & Analysis API` without weakening design/identification boundaries.

**Technical specification**
- Expose study/design/run endpoints with typed contracts.
- Never expose secrets or raw stack traces.

**Task-specific verification**
- [ ] API create/run/read contract tests.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.3: Streamlit Study Designer

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Streamlit Study Designer` without weakening design/identification boundaries.

**Technical specification**
- Create guided UI for treatment/outcome/estimand/DAG/assumptions.
- Prevent AnalysisReady transition on invalid design.

**Task-specific verification**
- [ ] Critical form flow smoke tests where practical.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.4: Diagnostics Dashboard

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Diagnostics Dashboard` without weakening design/identification boundaries.

**Technical specification**
- Visualize SRM, balance, overlap, weights, event studies and robustness artifacts.
- Keep plots traceable to AnalysisRun id.

**Task-specific verification**
- [ ] Dashboard data adapters tested.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.5: Estimator / Specification Comparison

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Estimator / Specification Comparison` without weakening design/identification boundaries.

**Technical specification**
- Compare estimates with estimand compatibility checks.
- Do not rank incompatible estimands as if identical.

**Task-specific verification**
- [ ] Mismatched estimands trigger warning/block.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.6: Assumption-Aware Report Generator

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Assumption-Aware Report Generator` without weakening design/identification boundaries.

**Technical specification**
- Generate standardized report per REPORTING_STANDARD.
- Include failed/unverifiable assumptions and interpretation status.

**Task-specific verification**
- [ ] Report fixture contains required sections.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 6.7: Analysis Registry, Re-Run & Reproducibility Bundle

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Analysis Registry, Re-Run & Reproducibility Bundle` without weakening design/identification boundaries.

**Technical specification**
- Persist runs and export config/data-hash/artifact manifest.
- Support rerun from bundle on fixture datasets.

**Task-specific verification**
- [ ] Fixture bundle reruns deterministically.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 7 — Simulation Benchmarking & Research Validation

### Task 7.1: Synthetic Data Generator with Known Effects

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Synthetic Data Generator with Known Effects` without weakening design/identification boundaries.

**Technical specification**
- Generate configurable RCT, confounded observational and panel DGPs.
- Persist true estimand for benchmark comparison.

**Task-specific verification**
- [ ] Seed reproducibility.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 7.2: Estimator Bias / RMSE Benchmark Harness

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Estimator Bias / RMSE Benchmark Harness` without weakening design/identification boundaries.

**Technical specification**
- Run Monte Carlo evaluation by estimator/DGP.
- Produce bias/RMSE and failure counts.

**Task-specific verification**
- [ ] Simple unbiased estimator benchmark passes tolerance.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 7.3: Confidence Interval Coverage Benchmark

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Confidence Interval Coverage Benchmark` without weakening design/identification boundaries.

**Technical specification**
- Estimate repeated-simulation CI coverage and width.
- Gate severe coverage regressions.

**Task-specific verification**
- [ ] Reference normal-means example near nominal coverage.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 7.4: Poor-Overlap & Extreme-Weight Stress Tests

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Poor-Overlap & Extreme-Weight Stress Tests` without weakening design/identification boundaries.

**Technical specification**
- Sweep overlap severity and measure instability/refusal behavior.
- Verify diagnostics activate before silent catastrophic extrapolation.

**Task-specific verification**
- [ ] Severe overlap fixture triggers block/warning.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 7.5: Nuisance Misspecification & Cross-Fitting Tests

**Status:** `[ ]` Not Started  
**Track:** `Advanced`

**Purpose**  
Deliver `Nuisance Misspecification & Cross-Fitting Tests` without weakening design/identification boundaries.

**Technical specification**
- Compare naive plug-in, AIPW and cross-fit paths under nuisance misspecification.
- Track bias/coverage.

**Task-specific verification**
- [ ] DGP demonstrates expected robustness pattern qualitatively.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 7.6: DiD / Experiment Failure-Mode Simulation Suite

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `DiD / Experiment Failure-Mode Simulation Suite` without weakening design/identification boundaries.

**Technical specification**
- Cover pre-trend violations, staggered heterogeneity, SRM, attrition and repeated-peeking misuse.
- Generate regression artifacts for CI.

**Task-specific verification**
- [ ] Failure modes are detected/labeled.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Phase 8 — Hardening, CI/CD & Operations

### Task 8.1: End-to-End Regression Suite

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `End-to-End Regression Suite` without weakening design/identification boundaries.

**Technical specification**
- Exercise design → estimate → diagnostics → report for each major family using fakes/fixtures.

**Task-specific verification**
- [ ] All supported family paths green.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 8.2: Observability & Health Checks

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Observability & Health Checks` without weakening design/identification boundaries.

**Technical specification**
- Add structured run/task logs and health/readiness endpoints.
- Scrub sensitive data.

**Task-specific verification**
- [ ] Health and log-scrub tests.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 8.3: Dockerization & Demo Stack

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Dockerization & Demo Stack` without weakening design/identification boundaries.

**Technical specification**
- Create reproducible local Docker/Compose path.
- Use fixture/demo datasets, never private data.

**Task-specific verification**
- [ ] Container health smoke test.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 8.4: GitHub Actions CI & Research Gates

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `GitHub Actions CI & Research Gates` without weakening design/identification boundaries.

**Technical specification**
- Run lint/types/tests/simulation smoke/security audit.
- Block merges on causal-regression test failures.

**Task-specific verification**
- [ ] Workflow syntax/quality gates validated.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

### Task 8.5: Operational Runbook, Security & Release Checklist

**Status:** `[ ]` Not Started  
**Track:** `Core`

**Purpose**  
Deliver `Operational Runbook, Security & Release Checklist` without weakening design/identification boundaries.

**Technical specification**
- Document recovery, result invalidation, dependency/security and release procedures.
- Include reproducibility and model-risk checklist.

**Task-specific verification**
- [ ] Release checklist complete on demo release.

**Common DoD**
- [ ] Implementation exists behind appropriate project contracts.
- [ ] Relevant unit/integration/simulation tests pass.
- [ ] Result provenance/configuration is persisted where applicable.
- [ ] No hidden estimand/assumption change is introduced.
- [ ] Documentation and `TASKS.md` are synchronized.

---

## Progress Summary

| Phase | Tasks | Core | Advanced | Completed |
|---|---:|---:|---:|---:|
| 1 Foundation, Causal Design & Reproducibility | 7 | 7 | 0 | 7 |
| 2 Randomized Experiments & Product Experimentation | 12 | 9 | 3 | 5 |
| 3 Observational Causal Inference & Double ML | 10 | 8 | 2 | 0 |
| 4 Difference-in-Differences & Policy Evaluation | 10 | 6 | 4 | 0 |
| 5 Sensitivity, Heterogeneity & Policy Value | 8 | 4 | 4 | 0 |
| 6 API, Dashboard & Reproducible Workflow | 7 | 7 | 0 | 0 |
| 7 Simulation Benchmarking & Research Validation | 6 | 5 | 1 | 0 |
| 8 Hardening, CI/CD & Operations | 5 | 5 | 0 | 0 |
| **Total** | **65** | **51** | **14** | **12** |
