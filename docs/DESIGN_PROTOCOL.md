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

Implemented by `causalimpact.design.DesignReadinessValidator`. Required for every family:
assignment mechanism, time zero, estimand, interference assessment, missingness plan,
inference unit, sensitivity plan and primary analysis, plus every family assumption from
`ASSUMPTION_CATALOG`, each with a justification and none marked violated. Additionally:

- randomized experiments: `randomization_unit`; a randomization unit that differs from the
  analysis unit requires a `cluster_variable`;
- observational studies: registered DAG and adjustment set that pass the backdoor check
  with no flagged variables, and overlap expectations.

## Observational study rule

Estimator selection follows identification. A propensity model is not a substitute for causal design.

## Experiment rule

The unit randomized, unit analyzed, exposure logging, and outcome logging must be explicitly distinguished.
