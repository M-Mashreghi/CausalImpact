# CausalImpact Evaluation Protocol

Causal estimator software must be validated on data-generating processes with known truth.

## Core benchmark outputs

- bias,
- RMSE,
- CI coverage,
- Type I error / false positive rate where applicable,
- interval width,
- failure / refusal rate,
- numerical stability.

## Stress scenarios

### Randomized
- zero effect,
- known positive / negative effect,
- SRM,
- missing outcomes,
- cluster assignment,
- heavy-tailed / ratio metrics,
- repeated monitoring misuse fixture.

### Observational
- measured confounding,
- correct and misspecified nuisance models,
- poor overlap,
- extreme weights,
- heterogeneous effects,
- unmeasured-confounding sensitivity scenarios.

### Panel / DiD
- valid parallel paths,
- divergent pre-trends,
- anticipation,
- staggered adoption,
- heterogeneous dynamic effects.

## Regression gate

Estimator changes should not merge if benchmark bias/coverage materially regresses without documented approval.
