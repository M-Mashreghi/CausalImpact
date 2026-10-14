# DAG & Identification Rules

- Represent key causal relationships explicitly using a DAG or documented causal graph.
- Adjustment sets must be derived from design logic, not automated feature importance.
- Never adjust for a collider merely because it predicts the outcome.
- Never adjust for a mediator in a total-effect analysis.
- Flag descendants of treatment as unsafe for standard pre-treatment adjustment.
- Store DAG / adjustment-set version with each AnalysisRun.
- Graph validation can assist researchers but cannot prove the DAG is correct.
