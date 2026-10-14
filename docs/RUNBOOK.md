# CausalImpact Operational Runbook

## Implausibly large effect

Check treatment/outcome definitions, duplicate units, assignment integrity, post-treatment variables, overlap, extreme weights, leakage, and subgroup composition.

## SRM detected

Treat the experiment as untrustworthy until root cause is resolved. Inspect assignment, exposure logging, telemetry loss, joins, triggered-analysis filters, and ramp configuration.

## Poor overlap

Report the failure. Inspect the target population and estimand. Consider a pre-specified restriction/ATT/ATC strategy. Never silently extrapolate.

## Differential attrition

Do not issue a clean experiment decision label. Inspect whether treatment affects missingness and document the resulting identification problem.

## DiD pre-period problem

Do not present the baseline DiD as cleanly causal. Revisit timing/comparison groups and use robust alternatives/limitations.

## Staggered-adoption mismatch

If treatment timing varies, verify that a heterogeneity-robust estimator is used rather than relying on naive TWFE event-study coefficients.

## Reproducibility failure

Verify data hash, design/DAG version, estimand, adjustment set, estimator, nuisance config, seed, inference config, and package versions.

## Result invalidation

If a bug affects prior estimates, mark affected AnalysisRun ids invalidated rather than overwriting history.
