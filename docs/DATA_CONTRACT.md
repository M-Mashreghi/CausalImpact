# CausalImpact Data Contract

## Canonical unit/event fields

```text
unit_id
timestamp
treatment
outcome
treatment_time
group
cluster_id
stratum
sample_weight
```

## Covariate metadata

Every adjustment candidate records:

```text
name
dtype
measurement_time
pre_treatment: true|false|unknown
descendant_of_treatment: true|false|unknown
missingness_policy
source
```

Unknown measurement timing blocks automatic inclusion in an adjustment set.

## Experiment metadata

```text
experiment_id
randomization_unit
analysis_unit
allocation_ratio
assignment_timestamp
exposure_timestamp
primary_metric
secondary_metrics
guardrail_metrics
planned_horizon
monitoring_policy
```

## Panel data

```text
unit_id
period
treated
treatment_start
outcome
covariates...
```

## Versioning

Every dataset used in an AnalysisRun should carry a content hash or immutable version identifier.
