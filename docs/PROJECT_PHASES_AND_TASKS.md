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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `CUPED / Pre-Period Variance Reduction` without weakening design/identification boundaries.

**Technical specification**
- Implement CUPED-style residualization from pre-treatment metric.
- Verify covariate is temporally prior and not treatment affected.

**Task-specific verification**
- [x] Known correlated pre-period fixture reduces variance.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/cuped.py` (`CupedITT`, `cuped_theta`). `EffectEstimate` gains a `details` dict for estimator provenance.
- Y_cv = Y − θ(X − mean X) with pooled θ = cov(Y, X)/var(X), then Welch difference in means of Y_cv; targets ITT only. `details` records the pre-metric, θ, the unadjusted SE, the variance ratio vs unadjusted and the outcome/pre-metric correlation.
- Temporal guard: the pre-period metric must be classified eligible (known pre-treatment and not a treatment descendant); unknown timing is refused, not warned. Categorical, missing, constant pre-metrics and using the outcome itself are refused.
- Tests: `tests/unit/experiments/test_cuped.py` (variance ratio ≈ 1 − ρ² = 0.36 at ρ = 0.8; θ equals the regression slope; no gain at ρ = 0; refusals; simulation: unbiased, coverage in [0.92, 0.98], variance < 50% of difference in means). Suite: 372 passed; ruff and mypy strict clean.
- Assumption/estimand changes: none (ITT preserved).

---

### Task 2.7: Power, MDE & Sample Size Engine

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Power, MDE & Sample Size Engine` without weakening design/identification boundaries.

**Technical specification**
- Implement power/MDE for supported metric types and allocation ratios.
- Keep planning calculations separate from post-hoc inference.

**Task-specific verification**
- [x] Reference examples match tolerance.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/power.py` (`PowerInputs`, `MetricType`, `power`, `sample_size`, `minimum_detectable_effect`, `standard_error`, `SampleSize`).
- Continuous and binary (unpooled) metrics, any treated fraction, two-sided α, optional pre-declared variance reduction (CUPED / adjustment). Binary MDE is solved numerically because the variance depends on the effect.
- Planning is separate from inference: inputs are assumed parameters only; no function accepts an observed estimate and no "observed power" is offered.
- Tests: `tests/unit/experiments/test_power.py` (Cohen d = 0.5 → 63 per arm; 10%→12% → 3839 per arm; power at planned n ≈ 0.80; size = α; MDE and sample size invert each other; allocation and variance-reduction scaling; validation; simulations confirm the planned 80% power is achieved by the actual difference-in-means and difference-in-proportions estimators). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 2.8: Guardrail Metrics & Multiple-Testing Policy

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Guardrail Metrics & Multiple-Testing Policy` without weakening design/identification boundaries.

**Technical specification**
- Support primary/secondary/guardrail metric roles.
- Implement approved multiplicity corrections and decision metadata.

**Task-specific verification**
- [x] Correction methods match reference fixtures.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/decision.py` (`CorrectionMethod`, `adjust_p_values`, `DecisionPolicy`, `GuardrailRule`, `Direction`, `guardrail_status`, `decide`, `Decision`, `DecisionLabel`, `GuardrailStatus`). Metric roles come from `ExperimentSpec` (one primary, secondary, guardrail; roles exclusive).
- Corrections: none, Bonferroni, Holm, Benjamini–Hochberg (R `p.adjust` semantics). Secondary metrics are reported with adjusted p-values and never drive the label. Guardrails are deliberately not adjusted (adjustment would hide harm); each needs a declared direction and tolerable degradation: violated if harm is significant, unresolved if the CI cannot rule out harm beyond tolerance.
- `decide` requires a policy declared before analysis (timestamp check), a rule for every guardrail, results for every metric at confidence 1 − α, and returns `blocked` if any trust diagnostic is blocking, else `no_ship` / `inconclusive` / `ship`, with reasons and the policy fingerprint.
- Tests: `tests/unit/experiments/test_decision.py` (two R `p.adjust` reference fixtures incl. ties and caps; all decision paths; guardrail directions; policy-timing, coverage and confidence-level validation). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Attrition & Missing-Outcome Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compare missingness/attrition by arm and over time.
- Block clean ship/no-ship labels when differential attrition is unresolved.

**Task-specific verification**
- [x] Differential attrition fixture triggers warning/block.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/experiments/attrition.py` (`check_attrition`).
- A randomization unit is attrited when absent from the analysis data or all its outcomes are missing. Reports per-arm assigned/attrited counts and rates, overall rate, chi-square test of independence (arm × attrited), the largest pairwise rate difference, and optional per-assignment-period rates.
- Blocking when differential attrition is detectable (p < α) or the rate difference exceeds the declared tolerance (default 0.01), so large differences in small experiments are not missed. A recorded `resolution` (e.g. bounds analysis) downgrades it to a visible warning, never removes it. High overall attrition and period-level differentials are warnings.
- Integrates with Task 2.8: a blocking attrition result makes `decide` return `blocked`.
- Tests: `tests/unit/experiments/test_attrition.py` (balanced passes; 5% vs 10% blocks; underpowered large difference blocks; absent units counted; resolution path; high overall; period-level flag; decision blocked). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Observational Covariate Temporal Eligibility` without weakening design/identification boundaries.

**Technical specification**
- Validate proposed adjustment variables against DAG and timing metadata.
- Produce allowed, forbidden and review-required covariate sets.

**Task-specific verification**
- [x] Mediator/collider/post-treatment fixtures flagged.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/eligibility.py` (`screen_adjustment_candidates`, `CovariateScreen`, `VariableDecision`).
- Combines temporal metadata (Task 1.3) with DAG structure (Task 1.5) into allowed / forbidden / review-required sets with reasons. Forbidden: treatment/outcome, mediator, treatment descendant, declared collider, unobserved node, or post-treatment / descendant by metadata. Review required: no metadata, unknown timing or descendant status, or not in the DAG. A metadata/DAG disagreement (metadata says pre-treatment, DAG says descendant) is forbidden and reported as a conflict.
- The allowed subset is also checked as a whole against the backdoor criterion, so individually acceptable variables that open a path (M-bias) or an unmeasured confounder leave `allowed_set_satisfies_backdoor = False` with the open paths listed. Nothing is added to the set automatically.
- Tests: `tests/unit/observational/test_eligibility.py` (confounder, mediator with conflicting metadata, post-treatment, declared selection collider, unobserved, treatment itself, not-in-DAG, unknown timing, missing metadata, M-bias set failure, unmeasured confounding). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 3.2: Propensity Score Estimation

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Propensity Score Estimation` without weakening design/identification boundaries.

**Technical specification**
- Implement baseline logistic propensity estimator behind interface.
- Persist predicted propensity and nuisance-model config.

**Task-specific verification**
- [x] Probabilities bounded and reproducible.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/propensity.py` (`PropensityModel` / `FittedPropensityModel` protocols, `LogisticPropensity`, `FittedLogistic`, `estimate_propensity`, `PropensityScores`, `ConvergenceError`); `covariate_matrix` moved to `src/causalimpact/estimators/design_matrix.py` so experiments and observational estimators share one eligibility-enforcing design builder.
- Baseline model: logistic regression by Newton–Raphson on standardised covariates, optional L2 penalty on slopes (never the intercept); no sklearn dependency. Scores are not clipped; divergence (complete separation, i.e. a positivity failure) raises `ConvergenceError` instead of returning 0/1 scores.
- Persistence: `PropensityScores` carries unit ids, treatment, scores (`to_frame()`), and a nuisance config (model, penalty, tolerances, covariates, design columns, coefficients on the original scale, iterations) with a content fingerprint.
- Tests: `tests/unit/observational/test_propensity.py` (bounded scores; coefficients recovered on a known DGP; scores equal an independent BFGS maximum-likelihood fit; identical across runs and row orders; penalty changes fingerprint and shrinks; separation raises; penalty resolves it; invalid inputs; post-treatment covariates refused). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 3.3: Overlap / Positivity Diagnostics

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Overlap / Positivity Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Plot/summarize treatment-specific propensity distributions.
- Compute overlap violations, support/effective sample diagnostics and refusal thresholds.

**Task-specific verification**
- [x] Poor-overlap fixture flagged.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/overlap.py` (`check_overlap`, `OverlapPolicy`, `ensure_overlap`, `OverlapRefusedError`, `estimand_weights`, `kish_ess`).
- Estimand-aware positivity: ATE checks all units in (ε, 1−ε); ATT only treated units below 1−ε; ATC only control units above ε. Reports violation counts/fraction, common-support interval and units outside it, Kish effective sample size of the estimand's IPW weights per arm, per-arm propensity quantiles and plot-ready histograms with bin edges.
- Thresholds are an explicit, recorded `OverlapPolicy` (default ε = 0.01; warn on any violation or ESS < 30%; block on > 5% violating or ESS < 10%). `ensure_overlap` raises `OverlapRefusedError` on a blocking result so estimators refuse instead of extrapolating.
- Tests: `tests/unit/observational/test_overlap.py` (good overlap passes; strong confounding blocks and refuses; ATT ignores irrelevant control-side violations that block ATE; warning band; plot data and policy recorded; weight/ESS formulas; simulation: violation fraction increases monotonically with confounding strength). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 3.4: Matching Engine & Matched-Sample Diagnostics

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Matching Engine & Matched-Sample Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Implement at least one transparent matching strategy.
- Report matched counts, distance quality and post-match balance.

**Task-specific verification**
- [x] Known toy match pairs are reproducible.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/matching.py` (`MatchingConfig`, `match_on_propensity`, `MatchResult`, `matched_sample_diagnostics`); `weighted_balance_rows` added to `src/causalimpact/diagnostics/balance.py` (weighted means, denominator from unweighted arm variances).
- Strategy: 1:k nearest-neighbour matching on the logit propensity score, with replacement (order-independent), caliper 0.2 SD of the logit score by default, deterministic tie-breaking by input order; targets the ATT. Matched-sample unit weights (treated 1, controls usage / k) are exposed for balance and later estimation. Matching without replacement is refused (order-dependent).
- Diagnostics: matched / unmatched treated counts, unique controls and maximum reuse, mean / max distance, caliper, SMD before and after matching (plus max |SMD|), and a warning when the caliper drops treated units, stating that the target population becomes the matched treated units.
- Tests: `tests/unit/observational/test_matching.py` (hand-checked toy pairs, reuse weights, caliper drop, 1:2 matching, order independence, max |SMD| on confounded data drops from > 0.3 to < 0.1, target-population change reported). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: caliper drops are surfaced as an explicit ATT-population restriction.

---

### Task 3.5: IPW / Stabilized / Overlap Weighting

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `IPW / Stabilized / Overlap Weighting` without weakening design/identification boundaries.

**Technical specification**
- Implement supported weighting schemes with explicit estimand mapping.
- Report weight distribution and effective sample size.

**Task-specific verification**
- [x] Weights normalize as documented.
- [x] Extreme-weight fixture surfaced.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/weighting.py` (`WeightScheme`, `SCHEME_ESTIMAND`, `compute_weights`, `normalized_weights`, `hajek_effect`, `weight_diagnostics`, `WeightingEstimator`). New `EstimandType.ATO` (overlap population) added to the estimand registry, because overlap weights do not target the ATE.
- Explicit scheme → estimand mapping enforced by `supported_estimands`: ipw / stabilized → ATE, att → ATT, atc → ATC, overlap → ATO. Hajek estimator (weights normalised to sum to one within each arm). Propensity-based schemes call the Task 3.3 overlap check and refuse when it is blocking; overlap weights (bounded by design) are still available.
- Uncertainty: nonparametric bootstrap of the whole pipeline (propensity re-estimated per replicate) with a seed derived from the run seed; > 5% failed replicates raises. `details` carries the scheme, propensity config and fingerprint, bootstrap settings, and the weight distribution (min / max / quantiles / CV, Kish ESS, max unit share, extreme-weight counts per arm).
- Tests: `tests/unit/observational/test_weighting.py` (hand-computed weights for all 5 schemes; within-arm normalisation; hand-computed Hajek effect; stabilized weights average 1; extreme-weight fixture warns; overlap weights cannot be reported as ATE; poor overlap refuses IPW but allows ATO; seeded bootstrap reproducible; simulation with heterogeneous effects: each scheme recovers its own estimand while the naive contrast is biased by > 1). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: ATO estimand added (documented above).

---

### Task 3.6: Outcome Regression Adjustment

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Outcome Regression Adjustment` without weakening design/identification boundaries.

**Technical specification**
- Implement regression-adjusted ATE/ATT baseline with explicit covariates.
- Keep nuisance prediction separate from causal effect object.

**Task-specific verification**
- [x] Known linear DGP recovers truth.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/outcome_regression.py` (`OutcomeLearner` / `FittedOutcomeModel` protocols, `LinearOutcomeModel`, `OutcomeNuisance`, `fit_outcome_nuisance`, `g_computation`, `OutcomeRegressionEstimator`).
- Nuisance and effect are separate: arm-specific outcome models μ₁, μ₀ live in `OutcomeNuisance` (no causal contrast); `g_computation` turns them into ATE (mean μ₁ − μ₀), ATT (treated: Y − μ₀) or ATC (controls: μ₁ − Y). Covariates go through the eligibility-enforcing design matrix.
- Uncertainty: seeded nonparametric bootstrap. Because regression extrapolates silently, the propensity overlap diagnostic for the same estimand is computed and attached to `details` (status and findings): surfaced, not used to refuse.
- Tests: `tests/unit/observational/test_outcome_regression.py` (nuisance recovers the DGP's arm-specific lines; ATE/ATT/ATC recovered on a known linear heterogeneous DGP; toy g-computation formulas; poor overlap surfaced; ATO refused; reproducible bootstrap; simulation coverage in [0.89, 0.99]). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 3.7: Doubly Robust AIPW Estimator

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Doubly Robust AIPW Estimator` without weakening design/identification boundaries.

**Technical specification**
- Implement AIPW with outcome and propensity nuisance models.
- Expose influence-function based uncertainty for supported iid case.

**Task-specific verification**
- [x] One correctly specified nuisance path remains approximately unbiased in simulation.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/observational/aipw.py` (`AIPWEstimator`, `aipw_scores`).
- AIPW for the ATE (Robins–Rotnitzky–Zhao score) and the ATT (doubly robust ATT score), using the outcome-nuisance and propensity interfaces from Tasks 3.2 and 3.6. Influence-function SE with a normal CI for the iid case. Overlap is checked first and blocking overlap refuses. Nuisances are fitted in-sample; `details` records `cross_fitting: false` and states that flexible ML learners require the cross-fitted engine (Task 3.8).
- Tests: `tests/unit/observational/test_aipw.py` (score reduces to Horvitz–Thompson IPW with a zero outcome model and to g-computation with zero residuals; ATE and ATT recovered with correct models; refusal on poor overlap; ATC refused; deterministic; simulations: outcome model wrong → AIPW unbiased while regression is biased ≈ −0.22; propensity model wrong → AIPW unbiased while IPW is biased ≈ +0.24; population-ATE coverage in [0.91, 0.98]).
- Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Covariate Balance & Weighted Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compute SMD before/after matching/weighting.
- Create Love-plot-ready data and balance thresholds.

**Task-specific verification**
- [x] Hand-computed SMD fixtures match.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: in `src/causalimpact/diagnostics/balance.py`: `weighted_balance_rows` (from Task 3.4), new `weighted_variance_ratio` and `balance_comparison`.
- Weighted SMD uses weighted arm means with the denominator from the unweighted arm variances, so before/after changes reflect mean shifts only. `balance_comparison` always includes an `unadjusted` baseline plus any labelled weightings (IPW, matching weights, …) and returns Love-plot-ready rows (adjustment, covariate, level, SMD, |SMD|, variance ratio for numeric covariates), per-adjustment summaries, and warnings for residual |SMD| > threshold (default 0.1) or variance ratios outside [0.5, 2] after adjustment.
- Tests: `tests/unit/observational/test_weighted_balance.py` (hand-computed weighted numeric SMD −1.1547, weighted binary SMD, weighted variance ratio 0.75 / 2.75; unit weights reproduce the unweighted SMD; invalid weights rejected; on confounded data max |SMD| goes from > 0.3 unadjusted to < 0.1 after both IPW and matching, with complete Love-plot data; residual imbalance flagged; reserved label). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Panel Data Contract & Treatment Timing Model` without weakening design/identification boundaries.

**Technical specification**
- Define unit-period schema, treatment start, never-treated/not-yet-treated flags.
- Validate treatment timing consistency.

**Task-specific verification**
- [x] Malformed timing fixtures fail.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/panel/contract.py` (`PanelSpec`, `PanelTiming`, `validate_panel`, `annotate_timing`).
- Unit–period schema with integer periods and a per-unit `treatment_start` (missing = never treated); optional 0/1 `treated` indicator, cluster and covariate columns. Absorbing treatment only (staggered adoption); non-absorbing patterns are refused.
- Blocking: missing columns, missing unit/period, non-integer periods or starts, duplicate (unit, period) rows, start varying within a unit, indicator disagreeing with period ≥ start, invalid indicator values, treatment switching off. Warnings: always-treated units (no pre-period), starts after the data window (not-yet-treated throughout), unbalanced panel, missing outcomes.
- `PanelTiming` summarises periods, cohort sizes, never/always-treated counts, balance and whether adoption is staggered; `annotate_timing` adds `ever_treated`, `never_treated`, `post`, `not_yet_treated` and `rel_time`.
- Tests: `tests/unit/panel/test_contract.py` (valid staggered panel; annotation; 9 malformed fixtures block; restrictive-timing warnings; unbalanced and missing-outcome warnings; indicator optional). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 4.2: Two-Period Difference-in-Differences

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Two-Period Difference-in-Differences` without weakening design/identification boundaries.

**Technical specification**
- Implement transparent 2x2 DiD estimand with uncertainty.
- Return group-time descriptive components.

**Task-specific verification**
- [x] Known-effect DGP recovered.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/panel/did.py` (`TwoPeriodDiD`).
- Targets the ATT only (identified under parallel trends and no anticipation, recorded as assumptions in `details`). DiD = mean unit first difference (treated) − mean unit first difference (comparison); comparison = never-treated plus not-yet-treated units (count reported). Welch/Neyman inference on unit first differences, i.e. clustered on unit. The four group-period means are returned as descriptive components.
- Refuses: invalid panel timing (Task 4.1 validation), units treated at or before the pre period, units missing either period, fewer than two units per group.
- Tests: `tests/unit/panel/test_did.py` (hand-computed 2x2 with components and SE; known effect recovered despite strong level selection where the cross-sectional contrast is biased by > 5; injected trend gap shows the estimate is not identified under a parallel-trends violation; refusals; simulation: unbiased, coverage in [0.92, 0.98]). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 4.3: Multi-Period DiD Baseline

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Multi-Period DiD Baseline` without weakening design/identification boundaries.

**Technical specification**
- Implement supported multi-period specification for non-staggered/controlled cases.
- Make comparison-group rules explicit.

**Task-specific verification**
- [x] Balanced panel fixture matches reference.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/panel/multi_period.py` (`SingleCohortDiD`, `ComparisonGroup`).
- Scope: one adoption cohort, balanced panel without gaps. The ATT averaged over post periods (equal weight per period) is computed as the difference in unit-level (post mean − pre mean) between treated and comparison units, which equals the static TWFE coefficient in this setting; unit-clustered Welch inference. Staggered adoption is refused with a pointer to the group-time estimator (Task 4.7); always-treated units and unbalanced panels are refused.
- Explicit comparison rule: `never_treated` (units starting after the window are excluded and counted) or `not_yet_treated` (they are included). Pre/post period counts and the rule are recorded in `details`.
- Tests: `tests/unit/panel/test_multi_period.py` (equals an independent two-way-demeaned TWFE reference to 1e-10; recovers the mean of dynamic effects (1, 2, 3); comparison rule changes the control set as documented; staggered and unbalanced refused; simulation: unbiased, coverage in [0.91, 0.98]). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 4.4: Classical Event-Study Diagnostic

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Classical Event-Study Diagnostic` without weakening design/identification boundaries.

**Technical specification**
- Produce relative-time coefficients for appropriate settings.
- Label as diagnostic/baseline and warn on staggered heterogeneous use.

**Task-specific verification**
- [x] Relative-time indexing correct.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/panel/event_study.py` (`relative_time`, `twfe_event_study`); `src/causalimpact/estimators/ols.py` gains `ols_cluster_robust` (CR1) and `two_way_demean` (exact two-way fixed effects on balanced panels).
- TWFE event study with relative-time dummies t − G_i, reference period (default −1) omitted and reported as 0, optional window with binned end points, never-treated units contributing only to the fixed effects, CR1 standard errors clustered by unit with t(G − 1) intervals.
- Labelled in its output as a "diagnostic baseline, not a causal dynamic-effect estimate". Staggered adoption adds a `twfe_event_study_staggered` warning citing contamination under heterogeneous effects (Sun & Abraham 2021) and pointing to Task 4.8. Unbalanced panels, an unobserved or out-of-window reference, and a single cohort without never-treated units are refused.
- Tests: `tests/unit/panel/test_event_study.py` (relative-time indexing; single cohort recovers zero pre-trends and dynamic effects 1/2/3 at the right indices; window binning; staggered flag; reference validation; demeaned regression equals the full unit + period dummy regression). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 4.5: Pre-Trend Diagnostics

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Pre-Trend Diagnostics` without weakening design/identification boundaries.

**Technical specification**
- Compute pre-period coefficients/joint diagnostics and plots.
- Report inability to prove parallel trends.

**Task-specific verification**
- [x] Injected pre-trend is detected in simulation.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/panel/pre_trends.py` (`check_pre_trends`); the event study (Task 4.4) now also exports its clustered coefficient covariance and coefficient order.
- Reports the pre-period coefficients (k < reference), max |pre coefficient|, the slope of a linear trend through them, and a joint Wald test with clustered covariance as F(q, G − 1). A significant joint test is blocking for a clean causal DiD interpretation (RUNBOOK "DiD pre-period problem"). Missing pre-periods yield a warning. Every result carries the caveat that a non-significant test does not prove parallel trends.
- Tests: `tests/unit/panel/test_pre_trends.py` (no-trend panel passes with caveat; injected trend blocks and its slope is recovered; hand-checked Wald / F / p-value; no-pre-period warning; input validation; simulation: false-positive rate ≤ 0.12 at α = 0.05 and detection ≥ 80% for a 0.15/period trend). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none (parallel trends stays an assumption).

---

### Task 4.6: Cluster-Robust Inference

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Cluster-Robust Inference` without weakening design/identification boundaries.

**Technical specification**
- Support cluster-robust SE configuration for panel estimators.
- Validate cluster count and warn for unsupported small-cluster inference.

**Task-specific verification**
- [x] Clustered DGP SE differs from naive iid as expected.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/estimators/clustering.py` (`ClusterPolicy`, `check_clusters`, `clustered_mean_difference`, `ensure_clusters`, `ClusterInferenceError`), `src/causalimpact/panel/inference.py` (`contrast_inference`, shared by the 2x2 and multi-period DiD estimators); CR1 OLS from Task 4.4. The event study now clusters on `PanelSpec.cluster` when declared.
- Configuration: `PanelSpec.cluster` selects the cluster level (default: the unit). Units must be nested in clusters. With a declared cluster, contrasts use CR1 with t(G − 1); without one, the unit-level Welch path is used. Cluster diagnostics (counts, sizes, treated clusters, findings) are attached to every estimate.
- Small-cluster policy (configurable): warn below 30 clusters, refuse below 5, and warn when fewer than 5 clusters are treated (Conley & Taber).
- Tests: `tests/unit/panel/test_clustering.py` (CR1 covariance vs hand computation; on a state-shock DGP the clustered SE is > 3× the naive SE; warn/refuse thresholds; estimator refuses 4 clusters; configurable policy; nesting enforced; event study clusters on state; simulation: naive coverage < 0.6, clustered coverage in [0.89, 0.99]). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Specification Robustness Runner` without weakening design/identification boundaries.

**Technical specification**
- Run approved alternative covariate/specification grids without hidden researcher degrees of freedom.
- Store every attempted spec, not only favorable ones.

**Task-specific verification**
- [x] All configured specs appear in output.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/sensitivity/specification.py` (`SpecificationVariant`, `SpecificationGrid`, `run_specifications`, `SpecificationReport`, `SpecificationOutcome`, `SpecStatus`).
- A grid is declared up front (timestamp, primary variant, content fingerprint over every variant's estimator definition) and must predate the run. Every declared variant is run against the same estimand and recorded in declaration order: `succeeded` (with the full estimate), `refused` (estimand mismatch, blocking overlap, too few clusters) or `failed` (with the error). Nothing is filtered, ranked or selected.
- Summary: counts by status, primary status, min/median/max estimate, share of CIs excluding zero, and share with the same sign as the primary.
- Tests: `tests/unit/sensitivity/test_specification.py` (five declared specs including a refused ATO variant and a failing one all appear in order with reasons; poor overlap recorded as refusal; run-before-declaration refused; fingerprint changes with the grid; grid validation). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Weight Trimming / Overlap Sensitivity` without weakening design/identification boundaries.

**Technical specification**
- Re-estimate across predeclared trimming/overlap policies.
- Track estimand/population changes caused by restriction.

**Task-specific verification**
- [x] Restricted sample/estimand metadata updates correctly.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/sensitivity/trimming.py` (`TrimmingPolicy`, `PolicyKind`, `trimmed_estimand`, `run_trimming_sensitivity`, `TrimmingReport`, `TrimmingOutcome`); `WeightingEstimator` gains an optional `truncation_quantile` with `truncate_weights` (within-arm caps), recorded in `details`.
- Policies are declared (timestamped, fingerprinted) before running. Propensity trimming (α ≤ e ≤ 1 − α) restricts the population, so it is reported against a derived estimand (`<id>__trim_<α>`, target population with the inclusion criterion added); the original estimand object is unchanged. Weight truncation keeps the population and estimand but is flagged as biasing the estimator. Per policy: kept / dropped counts overall and by arm, `population_changed`, estimate or recorded error. The trimming propensity model is fitted once on the full data and fingerprinted.
- Tests: `tests/unit/sensitivity/test_trimming.py` (derived estimand metadata; kept counts equal to an independent propensity computation; estimates carry the derived estimand id; truncation keeps the population and records its quantile; failures recorded; truncation requires a weighting estimator; within-arm caps; policy validation; declaration ordering). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: trimmed results are explicitly re-labelled with derived estimands.

---

### Task 5.4: Pre-Specified Subgroup Effects

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Pre-Specified Subgroup Effects` without weakening design/identification boundaries.

**Technical specification**
- Estimate subgroup effects only for declared groups using shared estimand.
- Report multiplicity/uncertainty.

**Task-specific verification**
- [x] Subgroup definitions are versioned and reproducible.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/heterogeneity/subgroups.py` (`SubgroupDefinition`, `SubgroupPlan`, `estimate_subgroups`, `subgroup_estimand`, `SubgroupReport`, `SubgroupResult`).
- Subgroups (by value set or numeric range) are declared in a timestamped plan with a content version; only declared subgroups are estimated, after the declaration time. Defining variables must be declared covariates known to be pre-treatment. Each subgroup uses the same estimator and estimand type, restricted via a derived estimand (`<id>__sub_<name>`, inclusion criterion recorded).
- Uncertainty and multiplicity: each subgroup's own interval; p-values adjusted across subgroups with the declared correction (default Holm); a Cochran Q homogeneity test when subgroups are disjoint (skipped with a reason otherwise). Failed subgroups are recorded with their error.
- Tests: `tests/unit/heterogeneity/test_subgroups.py` (declared-only results with derived estimands; known subgroup effect recovered; adjusted p-values equal the reference correction; Q test detects heterogeneity; overlap skips Q; version reproducible and changes with the plan; post-treatment variable refused; declaration ordering; failure recorded; definition validation). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: subgroup results carry derived, population-restricted estimands.

---

### Task 5.5: Exploratory Heterogeneity Guardrails

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Exploratory Heterogeneity Guardrails` without weakening design/identification boundaries.

**Technical specification**
- Separate exploratory findings from confirmatory results.
- Require holdout/cross-fitting or honest labeling of exploratory status.

**Task-specific verification**
- [x] Report labels exploratory results correctly.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/heterogeneity/exploratory.py` (`ExplorationConfig`, `candidate_subgroups`, `explore_subgroups`, `ExploratoryReport`, `ExploratoryFinding`); `EvidenceLabel` in `subgroups.py`, and pre-declared `SubgroupReport`s now carry `evidence_label = confirmatory`.
- Labels: `confirmatory` only for pre-declared plans (Task 5.4); `exploratory_holdout_validated` when subgroups are selected on a seeded discovery split and re-estimated on the untouched holdout (multiplicity-adjusted across the selected subgroups); `exploratory_unvalidated` when no holdout is used (hypothesis-generating, selection-biased). Discovery estimates are kept for transparency but never reported as evidence. Exploration variables must be known pre-treatment; candidates are categorical levels and numeric median splits; small or unestimable candidates cannot be selected.
- Tests: `tests/unit/heterogeneity/test_exploratory.py` (candidate enumeration; holdout and no-holdout labels and notes, never confirmatory; true heterogeneity recovered and significant on the holdout; seeded reproducibility; post-treatment variable refused; null simulation: selected subgroups' discovery deviation is > 1.5× their holdout deviation, i.e. the holdout removes selection inflation). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Core Causal Analysis Service` without weakening design/identification boundaries.

**Technical specification**
- Orchestrate design validation → estimator → diagnostics → report artifacts.
- Fail closed when required diagnostics block interpretation.

**Task-specific verification**
- [x] Happy path and blocked path integration tests.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/services/analysis.py` (`AnalysisService`, `DiagnosticStep`, `AnalysisResult`, `InterpretationStatus`, `interpret`); reusable end-to-end scenarios in `tests/integration/scenarios.py`.
- Orchestration order: re-run design readiness (must be AnalysisReady and still valid) → resolve the design's estimand from the registry → dataset content hash and a pinned `AnalysisRun` (estimator definition, diagnostics, seed, confidence level, code version) → trust diagnostics → `run_estimator` → `AnalysisResult` artifact (run + fingerprint, design, estimand, estimate, diagnostics, interpretation, reasons, assumptions, limitations).
- Fail closed: if any required diagnostic is blocking, estimation is withheld and the interpretation is "Causal interpretation not supported". Optional blocking diagnostics, warnings or assumptions with diagnostic concerns downgrade to "Suggestive". Estimator failures mark the run `failed` with the reason. Untestable assumptions are always listed as limitations. Interpretation labels are exactly the three in REPORTING_STANDARD.md.
- Tests: `tests/integration/test_analysis_service.py` (RCT happy path; SRM blocks and withholds the estimate; optional warning → suggestive; observational AIPW happy path; poor overlap blocks; estimator failure recorded on the run; non-ready design refused; identical inputs give identical fingerprints and estimates). Suite passed; ruff and mypy strict clean. Also added pytest-xdist for parallel runs (separate commit).
- Assumption/estimand changes: none.

---

### Task 6.2: FastAPI Study & Analysis API

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `FastAPI Study & Analysis API` without weakening design/identification boundaries.

**Technical specification**
- Expose study/design/run endpoints with typed contracts.
- Never expose secrets or raw stack traces.

**Task-specific verification**
- [x] API create/run/read contract tests.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/api/app.py` (`create_app`, `ApiState`, typed request/response models), `src/causalimpact/services/estimator_factory.py` (whitelisted, discriminated estimator configurations → estimators). Dependencies: `fastapi`, `uvicorn` (runtime, justified by this task) and `httpx2` (dev, TestClient transport). The `Estimator` protocol's `name` / `supported_estimands` became read-only properties so frozen estimators satisfy it.
- Endpoints: `GET /health`; `POST /estimands`, `GET /estimands/{id}`; `POST /dags`, `POST /adjustment-sets` (return content versions); `POST /designs` (Draft only), `GET /designs/{id}`, `POST /designs/{id}/transitions` (AnalysisReady runs the readiness validator); `POST /designs/{id}/runs` (estimator config, records, seed, confidence level, optional experiment spec adding SRM and attrition diagnostics; overlap diagnostic added automatically for propensity methods), `GET /runs/{id}`, `GET /designs/{id}/runs`.
- No causal computation in the API: it builds typed inputs and calls `AnalysisService`. Errors are typed bodies: 409 design-not-ready (with the problem list) and domain violations, 422 validation errors, 404 missing resources, and a generic 500 with an opaque error id that never returns messages, paths, settings or traces.
- Tests: `tests/integration/test_api.py` (RCT create → transition → run → read → list; SRM run "not supported"; readiness problems listed; draft run refused; observational run adds overlap diagnostic; 404/422 contract errors; 500 does not leak secrets; health). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 6.3: Streamlit Study Designer

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Streamlit Study Designer` without weakening design/identification boundaries.

**Technical specification**
- Create guided UI for treatment/outcome/estimand/DAG/assumptions.
- Prevent AnalysisReady transition on invalid design.

**Task-specific verification**
- [x] Critical form flow smoke tests where practical.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/dashboard/designer.py` (controller: `DesignForm`, `build_artifacts`, `register_and_promote`, `parse_edges`, `required_assumptions`, `PromotionOutcome`) and `src/causalimpact/dashboard/designer_app.py` (Streamlit page). Dependency: `streamlit` as the `dashboard` extra (also in dev for tests), justified by this task. `docs/DEPLOYMENT.md` documents how to start the designer and the API.
- Guided form for question, population, unit, treatment, outcome, estimand, identification fields, DAG edges / unobserved nodes / adjustment set / forbidden post-treatment variables, and a justification for each required assumption of the chosen family. Submitting registers the estimand, DAG and adjustment set and attempts Draft → Validated → AnalysisReady through `DesignReadinessValidator`; on failure the design stays Validated and every blocking problem is shown. The page holds no logic beyond layout.
- Tests: `tests/integration/test_designer.py` (complete observational form reaches AnalysisReady; mediator in adjustment set, insufficient set, missing time zero, unjustified assumptions and missing DAG each keep it out with the right problem; edge parsing; Streamlit `AppTest` smoke tests: incomplete design shows an error and no success, complete experiment shows AnalysisReady). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 6.4: Diagnostics Dashboard

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Diagnostics Dashboard` without weakening design/identification boundaries.

**Technical specification**
- Visualize SRM, balance, overlap, weights, event studies and robustness artifacts.
- Keep plots traceable to AnalysisRun id.

**Task-specific verification**
- [x] Dashboard data adapters tested.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/dashboard/adapters.py` (`diagnostic_summary_frame`, `srm_frame`, `balance_frame`, `overlap_frame`, `weights_frame`, `event_study_frame`, `specification_frame`) and `src/causalimpact/dashboard/diagnostics_app.py` (Streamlit page loading a saved `AnalysisResult` JSON).
- Adapters only reshape stored diagnostic numbers into tidy frames (SRM observed vs expected, Love-plot balance rows, per-arm propensity histograms, weight ESS / extremes, event-study coefficients with the "diagnostic baseline" label, specification outcomes with the grid fingerprint). Every frame carries `run_id`; every chart on the page is captioned with the AnalysisRun id and fingerprint; diagnostic findings are always shown. Wrong diagnostic types are rejected.
- Tests: `tests/integration/test_dashboard.py` (each adapter on real service / estimator outputs, including SRM counts summing to n, histogram counts summing to n, hand-checked SMD, event-study ordering and reference row; wrong-input rejection; Streamlit `AppTest` smoke test showing the run id and interpretation). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 6.5: Estimator / Specification Comparison

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Estimator / Specification Comparison` without weakening design/identification boundaries.

**Technical specification**
- Compare estimates with estimand compatibility checks.
- Do not rank incompatible estimands as if identical.

**Task-specific verification**
- [x] Mismatched estimands trigger warning/block.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/services/comparison.py` (`LabelledEstimate`, `compatibility_key`, `incompatibilities`, `ensure_comparable`, `compare_estimates`, `ComparisonReport`, `ComparisonGroup`).
- Estimates are comparable only with the same estimand type, treatment, outcome, scale, treatment basis, conditioning variables, target population and confidence level. Compatible estimates share a group (input order kept, differences from the first member reported); incompatible ones go to separate groups with a blocking `incompatible_estimands` finding listing each mismatch. `ensure_comparable` raises `EstimandMismatchError`. No ranking or "best" selection anywhere.
- Tests: `tests/unit/test_comparison.py` (AIPW and regression ATE grouped together; ATE / ATT / ATO split into three groups with a blocking finding; input order preserved; trimmed-population estimand incompatible; confidence-level mismatch; unique labels). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 6.6: Assumption-Aware Report Generator

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Assumption-Aware Report Generator` without weakening design/identification boundaries.

**Technical specification**
- Generate standardized report per REPORTING_STANDARD.
- Include failed/unverifiable assumptions and interpretation status.

**Task-specific verification**
- [x] Report fixture contains required sections.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/reporting/report.py` (`build_report`, `render_markdown`, `Report`, `Section`, `REQUIRED_SECTIONS`, `METHOD_REFERENCES`).
- Sections (always present, in this order): Interpretation status, Design (question, design family, treatment, outcome, population, estimand with averaging population and scale, DAG and adjustment-set versions), Result (estimate with units, interval, SE, p-value, inference method, estimator, sample sizes; or an explicit "no estimate" statement), Diagnostics (every diagnostic with required/optional and all findings, plus weight and overlap findings attached to estimates), Robustness (specification grid and trimming results when supplied; "not run" stated otherwise, including placebo and unmeasured-confounding sensitivity), Assumptions (testability, status, justification), Limitations (untestable assumptions, significance ≠ causality), Reproducibility (run id and status, fingerprint, design version and hash, dataset version, seed, confidence level, code version), Method references (from the estimator and diagnostics used).
- The interpretation label is copied from the analysis service and never upgraded.
- Tests: `tests/integration/test_report.py` (supported RCT report has every section and provenance; blocked SRM report says "not supported", has no estimate and lists the blocking finding; observational report renders specification and trimming artifacts and untestable assumptions). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 6.7: Analysis Registry, Re-Run & Reproducibility Bundle

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Analysis Registry, Re-Run & Reproducibility Bundle` without weakening design/identification boundaries.

**Technical specification**
- Persist runs and export config/data-hash/artifact manifest.
- Support rerun from bundle on fixture datasets.

**Task-specific verification**
- [x] Fixture bundle reruns deterministically.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/services/registry.py` (`AnalysisRegistry` on SQLite, `export_bundle`, `rerun_bundle`, `RerunCheck`, `BundleIntegrityError`, `load_bundle_data`) and `src/causalimpact/services/run_spec.py` (`RunSpec`, `DiagnosticsConfig`, `build_diagnostics`, `execute`): a declarative, serialisable run specification now shared by the API (6.2's request is a `RunSpec` plus data; the experiment spec moved under `diagnostics`).
- Registry: designs (per version), estimands (redefinition refused), DAGs, adjustment sets, and runs with their spec and full result. Append-only: `invalidate` records an event with a reason; the stored result is never overwritten; `runs()` reports invalidation status.
- Bundle: manifest (run id, fingerprint, dataset version, code version, SHA-256 of every artifact), design / estimand / DAG / adjustment-set / run-spec / result JSON, rendered report, dataset CSV and recorded dtypes. `rerun_bundle` verifies every file hash and the reloaded dataset's content hash (round-trip float parsing), re-runs through the service and checks fingerprint, estimate and interpretation.
- Tests: `tests/integration/test_registry.py` (RCT and observational/DAG bundles rerun with identical fingerprint and estimate; tampered data rejected; registry round-trip after reopening; invalidation preserves history; estimand redefinition refused; mixed dtypes round-trip). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

## Phase 7 — Simulation Benchmarking & Research Validation

### Task 7.1: Synthetic Data Generator with Known Effects

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Synthetic Data Generator with Known Effects` without weakening design/identification boundaries.

**Technical specification**
- Generate configurable RCT, confounded observational and panel DGPs.
- Persist true estimand for benchmark comparison.

**Task-specific verification**
- [x] Seed reproducibility.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/simulation/dgp.py` (`RCTConfig`, `ObservationalConfig`, `PanelConfig`, discriminated `SimulationConfig`, `simulate`, `SimulatedDataset` with `manifest()` / `save()`).
- RCT: individual or cluster randomisation, continuous or binary outcome, heterogeneity, prognostic covariate, realised-share deviation (SRM) and arm-specific attrition. Observational: confounding strength, heterogeneous effects, optional nonlinear outcome / propensity (for misspecification studies). Panel: staggered cohorts, never-treated share, dynamic and cohort-scaled effects, pre-trend slope, anticipation, clustered shocks.
- Truths are sample-level averages of the known unit effects (ITT/ATE, ATT, ATC, ATO with the true propensity; panel post-period ATT and dynamic effects) plus closed-form population values where available. The random stream is derived from the seed per DGP kind. `save()` persists data and a manifest with config, seed, dataset content hash and truths.
- Tests: `tests/simulation/test_dgp.py` (seed reproducibility for all three kinds; persisted truth manifest; RCT truth and SRM / attrition / cluster switches; ATT > ATE > ATC under heterogeneity; confounded naive contrast; generated panel passes timing validation as staggered and balanced; injected pre-trend slope recovered). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 7.2: Estimator Bias / RMSE Benchmark Harness

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Estimator Bias / RMSE Benchmark Harness` without weakening design/identification boundaries.

**Technical specification**
- Run Monte Carlo evaluation by estimator/DGP.
- Produce bias/RMSE and failure counts.

**Task-specific verification**
- [x] Simple unbiased estimator benchmark passes tolerance.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/simulation/benchmark.py` (`BenchmarkCase`, `run_benchmark`, `BenchmarkResult`, `bias_within_tolerance`).
- Each replicate simulates fresh data from a replicate seed derived from the benchmark seed, builds the estimator for that seed, runs it through `run_estimator` and compares with that replicate's truth. Reports bias with Monte Carlo SE, RMSE, empirical SD, mean reported SE, failure counts by exception type and failure rate, and keeps per-replicate estimates, truths, SEs and CIs (used for coverage in Task 7.3). Failures are counted, never dropped; a result with no successes cannot pass the bias tolerance.
- Tests: `tests/simulation/test_benchmark.py` (difference in means is unbiased within tolerance with RMSE ≈ SD and mean SE ≈ empirical SD; reproducible by seed; attrition-induced refusals counted as failures; confounded naive contrast fails the tolerance). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 7.3: Confidence Interval Coverage Benchmark

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Confidence Interval Coverage Benchmark` without weakening design/identification boundaries.

**Technical specification**
- Estimate repeated-simulation CI coverage and width.
- Gate severe coverage regressions.

**Task-specific verification**
- [x] Reference normal-means example near nominal coverage.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/simulation/coverage.py` (`coverage_summary`, `CoverageSummary`, `CoverageGate`, `check_coverage`), built on the per-replicate CIs from the Task 7.2 harness.
- Coverage is computed against each replicate's own truth, with Monte Carlo SE, mean interval width and failure rate. The gate blocks severe under-coverage (below nominal − 0.05 by default), drops of more than 0.03 versus a stored baseline, and failure rates above 5%, so refusals cannot hide poor coverage. Coverage with zero successful replicates is undefined and raises.
- Tests: `tests/simulation/test_coverage.py` (difference-in-means normal-means reference within 3 MC SE of 0.95 and passes the gate; unit-level SEs on cluster-randomised data cover < 0.8 and are blocked; baseline regression blocked; failure-rate gate; 2x2 DiD on a simulated panel passes). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 7.4: Poor-Overlap & Extreme-Weight Stress Tests

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Poor-Overlap & Extreme-Weight Stress Tests` without weakening design/identification boundaries.

**Technical specification**
- Sweep overlap severity and measure instability/refusal behavior.
- Verify diagnostics activate before silent catastrophic extrapolation.

**Task-specific verification**
- [x] Severe overlap fixture triggers block/warning.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/simulation/stress.py` (`overlap_sweep`, `StressPoint`).
- Sweeps confounding strength on the observational DGP. Per replicate: overlap diagnostic status (propensity separation counts as blocking), estimator refusal, error versus truth, catastrophic-error flag (absolute error threshold). Per strength: status counts, refusals, failures, bias, RMSE, max error, catastrophic count and the safety metric `n_catastrophic_unflagged` (catastrophic errors on replicates whose overlap check passed).
- Tests: `tests/simulation/test_stress.py` (guarded IPW: mild overlap passes with no refusals, severe overlap blocks ≥ 90% of replicates and refuses ≥ 90%, refusal rate increases monotonically; unguarded IPW with refusal disabled does break down, yet no catastrophic error occurs on a replicate with a passing overlap diagnostic, and RMSE grows > 3× from mild to severe). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

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

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `DiD / Experiment Failure-Mode Simulation Suite` without weakening design/identification boundaries.

**Technical specification**
- Cover pre-trend violations, staggered heterogeneity, SRM, attrition and repeated-peeking misuse.
- Generate regression artifacts for CI.

**Task-specific verification**
- [x] Failure modes are detected/labeled.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/simulation/failure_modes.py` (`run_failure_mode_suite`, `FailureModeReport` with `write()` for a JSON CI artifact, `ScenarioResult`).
- Scenarios (each with a clean control): SRM (realised share 0.46 vs 0.5) → `check_srm`; differential attrition (10% treated-only loss vs equal 5%) → `check_attrition`; pre-trend violation (0.3/period drift vs parallel) → event study + `check_pre_trends`; staggered heterogeneous adoption (two cohorts, 1× vs 3× effects vs single cohort) → TWFE event-study staggered flag. Detection rates are computed over seeded replicates.
- Repeated peeking is a demonstration only: a null RCT monitored at 10 fixed-horizon looks shows the inflated false-positive rate; automatic detection belongs to the deferred Advanced Task 2.12 and the scenario is labelled `detector="not implemented (Task 2.12)"` rather than claimed.
- Tests: `tests/simulation/test_failure_modes.py` (all four failure modes detected ≥ 90%; controls alarm ≤ 25%; peeking false-positive rate > 0.12 and honestly labelled; JSON artifact round-trips). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

## Phase 8 — Hardening, CI/CD & Operations

### Task 8.1: End-to-End Regression Suite

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `End-to-End Regression Suite` without weakening design/identification boundaries.

**Technical specification**
- Exercise design → estimate → diagnostics → report for each major family using fakes/fixtures.

**Task-specific verification**
- [x] All supported family paths green.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `tests/e2e/test_end_to_end.py` and a panel scenario in `tests/integration/scenarios.py`. To let every family run through the same declarative path, `TwoPeriodDiDConfig` / `SingleCohortDiDConfig` were added to the estimator factory, and `DiagnosticsConfig.pre_trends` adds an event-study pre-trend check for multi-period DiD. A circular import between reporting and the services package was removed (lazy import in `export_bundle`).
- Each family (randomized: difference in means with SRM and attrition; observational: AIPW with overlap; panel: single-cohort DiD with pre-trends) runs design → `RunSpec` → service → diagnostics → estimate within 4 SE of the simulated truth → report with all required sections → bundle export → deterministic rerun. Each family's blocked path (SRM, poor overlap, injected pre-trend) withholds the estimate and reports "Causal interpretation not supported" with the blocking diagnostic.
- Verification found a wrong hand-written truth for the panel case (2.0 instead of 2.25 for post-period effects 1, 2, 3, 3); the test now uses the correct value.
- Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 8.2: Observability & Health Checks

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Observability & Health Checks` without weakening design/identification boundaries.

**Technical specification**
- Add structured run/task logs and health/readiness endpoints.
- Scrub sensitive data.

**Task-specific verification**
- [x] Health and log-scrub tests.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `src/causalimpact/config/settings.py` (`Settings.from_env`: env, DB URL, log level), `src/causalimpact/config/observability.py` (`configure_logging`, `log_event`, `JsonFormatter`, `ScrubFilter`, `scrub`, `scrub_text`); the analysis service logs `analysis_run_started` / `analysis_run_finished` (run id, design, estimand, estimator, dataset version, row count, status, interpretation, blocked diagnostics, duration; no data values); the API adds `GET /ready` (registry reachability; 503 when unavailable; returns environment and component status only, never configuration values) next to `GET /health`, and logs unhandled errors as structured events with the error id and type only. `AnalysisRegistry.ping()` added; `.env.example` gains `CAUSALIMPACT_LOG_LEVEL`.
- Scrubbing: sensitive keys at any nesting depth (password, secret, token, API key, authorization, cookie, credentials, DB URL / DSN), key=value pairs and bearer tokens in free text, and user:password credentials in URLs are redacted before formatting; exceptions are logged by type only.
- Tests: `tests/integration/test_observability.py` (five secret patterns scrubbed; nested field scrubbing; JSON log records; run lifecycle events; health and readiness with and without a registry, no leakage of the DB path; unavailable registry → 503; settings from env; logging configuration). Suite passed; ruff and mypy strict clean.
- Assumption/estimand changes: none.

---

### Task 8.3: Dockerization & Demo Stack

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `Dockerization & Demo Stack` without weakening design/identification boundaries.

**Technical specification**
- Create reproducible local Docker/Compose path.
- Use fixture/demo datasets, never private data.

**Task-specific verification**
- [x] Container health smoke test.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `Dockerfile` (python:3.12-slim, hash-locked `requirements.lock` exported from `uv.lock`, non-root user, HEALTHCHECK on `/health`, synthetic demo data generated at build), `docker-compose.yml` (API :8000 with a persistent SQLite volume, dashboard :8501 gated on API health), `.dockerignore` (no data, `.env` or databases), `scripts/make_demo_data.py`, `scripts/smoke_container.sh`, and `causalimpact.api.server:build_app` (settings, logging, persistent registry; designs and runs survive restarts).
- Local tests: `tests/integration/test_deployment.py` (production app health/readiness and persistence across restarts, demo data script, Dockerfile/compose invariants, `requirements.lock` matches `uv.lock`).
- Container health smoke test: Docker is not installed on the build machine, so it ran in CI — GitHub Actions run 38630394434 (commit 4ad8de9), job "container health smoke test": build, compose up, `/health`, `/ready`, dashboard health — passed.
- Assumption/estimand changes: none.

---

### Task 8.4: GitHub Actions CI & Research Gates

**Status:** `[x]` Completed  
**Track:** `Core`

**Purpose**  
Deliver `GitHub Actions CI & Research Gates` without weakening design/identification boundaries.

**Technical specification**
- Run lint/types/tests/simulation smoke/security audit.
- Block merges on causal-regression test failures.

**Task-specific verification**
- [x] Workflow syntax/quality gates validated.

**Common DoD**
- [x] Implementation exists behind appropriate project contracts.
- [x] Relevant unit/integration/simulation tests pass.
- [x] Result provenance/configuration is persisted where applicable.
- [x] No hidden estimand/assumption change is introduced.
- [x] Documentation and `TASKS.md` are synchronized.

**Completion record**
- Implementation: `.github/workflows/ci.yml` with jobs `quality` (ruff check, ruff format --check, mypy strict), `tests` (non-simulation suite, parallel), `research-gates` (simulation suite plus `scripts/research_gates.py`: known-truth bias and coverage gates for difference in means, AIPW and 2x2 DiD, failure-mode detection and control false-alarm gates; JSON artifact uploaded), `security` (`uv lock --check`, `requirements.lock` ↔ `uv.lock` diff, `pip-audit --strict`), `container` (Docker smoke test), and `ci-gate`, which fails if any job failed, was cancelled or skipped. Read-only permissions, version-pinned actions, no secrets (mandatory CI has no external credentials). PyYAML added as a dev dependency to validate the workflow and compose files.
- Verification: `tests/integration/test_ci_workflow.py` (workflow parses; required jobs and gates present; gate job semantics; pinned actions; no secrets; compose parses; research-gates script passes). First GitHub Actions run 38630394434 on commit 4ad8de9: all six jobs succeeded.
- Blocking merges requires marking `ci-gate` as a required status check in the repository's branch-protection settings (a repository setting, documented in the workflow header).
- Assumption/estimand changes: none.

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
| 2 Randomized Experiments & Product Experimentation | 12 | 9 | 3 | 9 |
| 3 Observational Causal Inference & Double ML | 10 | 8 | 2 | 8 |
| 4 Difference-in-Differences & Policy Evaluation | 10 | 6 | 4 | 6 |
| 5 Sensitivity, Heterogeneity & Policy Value | 8 | 4 | 4 | 4 |
| 6 API, Dashboard & Reproducible Workflow | 7 | 7 | 0 | 7 |
| 7 Simulation Benchmarking & Research Validation | 6 | 5 | 1 | 5 |
| 8 Hardening, CI/CD & Operations | 5 | 5 | 0 | 4 |
| **Total** | **65** | **51** | **14** | **50** |
