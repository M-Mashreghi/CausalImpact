# Testing Rules

Use synthetic known-effect datasets whenever possible.

Mandatory families include:

- schema and temporal-variable validation,
- DAG / adjustment-set guards,
- deterministic seeding,
- SRM,
- estimator sanity checks,
- overlap / weight diagnostics,
- cross-fitting reproducibility,
- DiD known-effect simulations,
- staggered-adoption simulations,
- pre-trend violations,
- bootstrap / CI coverage,
- API contracts.

Mandatory CI must not depend on external APIs.
