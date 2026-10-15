# CausalImpact

**An estimand-first, assumption-aware platform for causal inference and experimentation.**

[![ci](https://github.com/M-Mashreghi/CausalImpact/actions/workflows/ci.yml/badge.svg)](https://github.com/M-Mashreghi/CausalImpact/actions/workflows/ci.yml)

Most analytics code answers "what number does this regression print?". CausalImpact
answers "what is the causal effect, under which assumptions, and how much should we trust
it?". It makes you state the question precisely before any model runs, checks the data
and the design before estimating, and refuses to label a result causal when its
diagnostics fail.

```text
Question → Design + DAG → Estimand → Identification → Diagnostics → Estimator
        → Sensitivity / robustness → Assumption-aware report (+ reproducibility bundle)
```

## What it does

You describe a study (treatment, outcome, population, assignment mechanism, causal
graph, assumptions) and provide a dataset. CausalImpact then:

1. **Validates the design.** A study cannot be analysed until every identification
   field is filled in and every required assumption is justified. Adjustment sets are
   checked against your DAG (mediators, colliders, post-treatment variables are refused).
2. **Runs trust diagnostics first.** Sample-ratio mismatch, assignment integrity,
   attrition, covariate balance, propensity overlap, pre-trends, cluster counts.
   A blocking diagnostic **withholds the estimate** instead of reporting a misleading one.
3. **Estimates the declared estimand** (ITT, ATE, ATT, ATC, ATO) with an estimator that
   is allowed to target it. Estimators cannot silently switch estimands.
4. **Reports** the estimate with uncertainty, every diagnostic, the assumptions (marked
   testable or untestable), robustness checks, limitations and full provenance.
5. **Makes it reproducible.** Every run has a fingerprint over data, design, estimator,
   seed and code version, and can be exported as a bundle that re-runs bit-for-bit.

## Outputs

| Output | What it is | Where |
|---|---|---|
| Effect estimate | point estimate, SE, CI, p-value, sample sizes, estimand id | `AnalysisResult.estimate` / API JSON |
| Interpretation status | exactly one of *Causal estimate supported under stated assumptions*, *Suggestive; important diagnostics/assumptions unresolved*, *Causal interpretation not supported* | every result and report |
| Diagnostics | SRM, attrition, balance (Love-plot data), overlap histograms and ESS, weight distributions, event-study and pre-trend tests | `AnalysisResult.diagnostics`, dashboard |
| Report | Markdown report with design, result, diagnostics, robustness, assumptions, limitations, reproducibility, method references | `report.md` in each bundle |
| Reproducibility bundle | data + design + estimand + DAG + run spec + result + report, all SHA-256 hashed | `export_bundle` / `rerun_bundle` |
| Registry | SQLite store of designs, runs and invalidation history (runs are never overwritten) | `data/causalimpact.db` |
| Benchmarks | bias, RMSE and CI-coverage of estimators on simulated data with known truth | `scripts/research_gates.py` |

## Typical uses

| You want to… | Use | Estimand |
|---|---|---|
| Decide whether to ship an A/B test | SRM + attrition checks, difference in means/proportions, CUPED or regression adjustment, guardrails with multiple-testing correction, ship / no-ship / inconclusive / blocked label | ITT |
| Size an experiment before launch | power, MDE and sample-size engine (continuous or binary metrics, unequal allocation, CUPED gain) | planning only |
| Evaluate a programme without randomisation | DAG-checked adjustment set, propensity scores, overlap diagnostics, matching, IPW / overlap weights, outcome regression, doubly robust AIPW | ATE / ATT / ATC / ATO |
| Estimate the effect of a shock on a single unit (one country, region, firm) | synthetic control with in-space and in-time placebo tests (see [examples/iran_sanctions](examples/iran_sanctions)) | ATT of the treated unit |
| Evaluate a policy rolled out at one point in time | panel validation, 2x2 and multi-period difference-in-differences, event study, pre-trend test, cluster-robust SEs | ATT |
| Check how fragile a result is | pre-declared specification grid (every spec reported), trimming / truncation sensitivity, estimator comparison with estimand-compatibility checks | — |
| Look for heterogeneous effects | pre-specified subgroups (confirmatory) vs. holdout-validated exploration (always labelled exploratory) | subgroup ITT/ATE |
| Validate a method before trusting it | simulated data with known effects, bias / coverage benchmarks, overlap stress tests, failure-mode suite | — |

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) (installs Python 3.12 and locked dependencies).

```bash
git clone https://github.com/M-Mashreghi/CausalImpact.git
cd CausalImpact
uv sync --extra dev

uv run pytest -m "not simulation" -n 6            # tests (~1 min)
uv run python scripts/demo_release.py              # 3 demo analyses -> artifacts/demo_release/
uv run python examples/ab_test.py                  # a full A/B analysis in Python, prints the report
```

Run your own study from a CSV file and a JSON study file (estimand, design, assumption
justifications, estimator):

```bash
uv run python scripts/run_analysis.py --data my_data.csv --study my_study.json --out results/my_study
```

[`examples/iran_sanctions/study.json`](examples/iran_sanctions/study.json) is a complete
study file to copy from.

Interactive tools:

```bash
uv run streamlit run src/causalimpact/dashboard/designer_app.py      # study designer
uv run streamlit run src/causalimpact/dashboard/diagnostics_app.py   # diagnostics (enter a bundle folder)
uv run uvicorn --factory causalimpact.api.server:build_app           # HTTP API, docs at /docs
docker compose up --build                                            # API :8000 + dashboard :8501
```

Step-by-step guide for Windows: [docs/QUICKSTART.md](docs/QUICKSTART.md).

## Using it from Python

[`examples/ab_test.py`](examples/ab_test.py) is a complete, runnable example. In short:

```python
design = StudyDesign(...)                      # question, treatment, outcome, population,
                                               # assignment, assumptions with justifications
design = design.transition(VALIDATED, ...).transition(
    ANALYSIS_READY, readiness_check=DesignReadinessValidator(estimands, dags))

spec = RunSpec(estimator=DifferenceInMeansConfig(treatment=...),
               diagnostics=DiagnosticsConfig(experiment=...), seed=1)
result = execute(AnalysisService(estimands, dags), design, spec, data)

print(result.interpretation, result.estimate)
print(render_markdown(build_report(result)))
```

## Using it over HTTP

```text
POST /estimands                      register the target estimand
POST /dags, /adjustment-sets         register the causal graph and adjustment set
POST /designs                        create a study design (Draft)
POST /designs/{id}/transitions       Draft -> Validated -> AnalysisReady (validated)
POST /designs/{id}/runs              run: estimator config + records + diagnostics
GET  /runs/{id}                      full result: estimate, diagnostics, interpretation
GET  /health, /ready                 liveness and readiness
```

## Data you need

- **Experiments:** one row per unit with an id, the assigned arm and the outcome
  (optionally pre-period covariates). Arms and allocation are declared up front.
- **Observational studies:** one row per unit with a 0/1 treatment, the outcome and
  pre-treatment covariates, each declared with its measurement timing.
- **Panels:** one row per unit × period with `unit_id`, `period`, `treatment_start`
  (empty for never-treated units) and `outcome`.

## What it will not do

- It does not take a question in plain language; you must define the design.
- It never proves an assumption: unconfoundedness and parallel trends are reported as
  assumptions, and diagnostics can only weaken or support them.
- It refuses rather than extrapolates: poor overlap, sample-ratio mismatch, differential
  attrition or a detected pre-trend block the causal label.

## Status

The full **Core** track is complete, plus synthetic control and placebo tests (53 of 65
planned tasks, 700+ tests, CI with known-truth research gates). Not yet implemented
(**Advanced** track): cross-fitted double ML, heterogeneity-robust staggered DiD,
sequential monitoring, clustered/ratio-metric experiment inference, CATE learners,
unmeasured-confounding sensitivity.
Progress: [docs/TASKS.md](docs/TASKS.md).

## Documentation

| Document | Contents |
|---|---|
| [QUICKSTART](docs/QUICKSTART.md) | install and try everything locally |
| [ARCHITECTURE](docs/ARCHITECTURE.md) | layers, contracts, invariants |
| [DESIGN_PROTOCOL](docs/DESIGN_PROTOCOL.md) | what a design must contain |
| [CAUSAL_ASSUMPTIONS](docs/CAUSAL_ASSUMPTIONS.md) | assumptions per design family |
| [REPORTING_STANDARD](docs/REPORTING_STANDARD.md) | what every report contains |
| [EVALUATION_PROTOCOL](docs/EVALUATION_PROTOCOL.md) | how estimators are validated |
| [RUNBOOK](docs/RUNBOOK.md) | operations, recovery, result invalidation |
| [SECURITY](docs/SECURITY.md) | secrets, logging, dependencies |
| [PROJECT_PHASES_AND_TASKS](docs/PROJECT_PHASES_AND_TASKS.md) | full task plan with completion records |

## Tech stack

Python 3.12 · numpy / pandas / scipy (transparent estimator implementations) · pydantic ·
FastAPI · Streamlit · SQLite · pytest · Docker · GitHub Actions.
