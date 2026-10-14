# CausalImpact Study Design Protocol

A new analysis should be created from a design record before estimation code is selected.

## Required design fields

- research question,
- target population,
- unit of analysis,
- treatment / exposure,
- outcome,
- assignment / exposure mechanism,
- time zero / treatment timing,
- estimand,
- causal DAG version,
- proposed adjustment set,
- forbidden post-treatment variables,
- interference assessment,
- missingness / attrition plan,
- overlap expectations,
- inference unit / clustering,
- sensitivity plan,
- primary and secondary analyses.

## Design statuses

```text
Draft → Validated → AnalysisReady → Estimated → Reviewed → Reported
```

`AnalysisReady` should fail closed when core fields are missing.

## Observational study rule

Estimator selection follows identification. A propensity model is not a substitute for causal design.

## Experiment rule

The unit randomized, unit analyzed, exposure logging, and outcome logging must be explicitly distinguished.
