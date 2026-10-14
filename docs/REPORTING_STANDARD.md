# CausalImpact Reporting Standard

Every analysis report must include:

## Design
- research question,
- treatment,
- outcome,
- population,
- estimand,
- study design,
- DAG / adjustment set.

## Result
- point estimate,
- uncertainty interval,
- inference method,
- sample size / effective sample size,
- units of effect.

## Diagnostics
Relevant examples:
- SRM,
- baseline balance,
- attrition,
- overlap,
- weighted balance,
- effective sample size,
- pre-treatment fit,
- pre-trend/event-study diagnostics.

## Robustness
- alternative specifications,
- trimming / weighting sensitivity,
- placebo / falsification checks,
- unmeasured-confounding sensitivity where applicable.

## Interpretation status

Use one of:

- `Causal estimate supported under stated assumptions`
- `Suggestive; important diagnostics/assumptions unresolved`
- `Causal interpretation not supported`

Never convert statistical significance alone into a “causal” label.
