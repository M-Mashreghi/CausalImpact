# CausalImpact — Project Structure

```text
CausalImpact/
├── CLAUDE.md
├── README.md
├── PROJECT_STRUCTURE.md
├── pyproject.toml
├── .env.example
├── .gitignore
│
├── .claude/rules/
│   ├── architecture.md
│   ├── causal-integrity.md
│   ├── dag-identification.md
│   ├── randomized-experiments.md
│   ├── sequential-experimentation.md
│   ├── observational-studies.md
│   ├── panel-policy.md
│   ├── statistics.md
│   ├── testing.md
│   └── documentation.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DESIGN_PROTOCOL.md
│   ├── DATA_CONTRACT.md
│   ├── CAUSAL_ASSUMPTIONS.md
│   ├── EVALUATION_PROTOCOL.md
│   ├── REPORTING_STANDARD.md
│   ├── ROADMAP.md
│   ├── PHASES.md
│   ├── PROJECT_PHASES_AND_TASKS.md
│   ├── TASKS.md
│   ├── DIAGRAMS.md
│   ├── DEPLOYMENT.md
│   ├── RUNBOOK.md
│   ├── REFERENCES.md
│   └── REVIEW_NOTES_v2.md
│
├── src/causalimpact/
│   ├── config/
│   ├── domain/
│   ├── ingestion/
│   ├── validation/
│   ├── design/
│   ├── dags/
│   ├── experiments/
│   ├── observational/
│   ├── panel/
│   ├── estimators/
│   ├── diagnostics/
│   ├── sensitivity/
│   ├── heterogeneity/
│   ├── simulation/
│   ├── reporting/
│   ├── services/
│   ├── api/
│   └── dashboard/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── simulation/
│   └── e2e/
│
├── data/{raw,processed,fixtures}/
├── artifacts/{estimates,diagnostics,reports,repro_bundles}/
├── notebooks/exploration/
├── scripts/
└── .github/workflows/{ci.yml,cd.yml}
```

Notebooks are exploratory only. Reusable causal logic belongs in `src/causalimpact/`.
