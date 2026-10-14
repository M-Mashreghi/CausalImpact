# Causal Assumptions Registry

Every analysis records assumptions explicitly.

## Randomized experiments

Potential assumptions / design conditions:

- valid assignment mechanism,
- correct exposure and outcome logging,
- no invalidating interference,
- interpretable attrition / missing outcomes,
- analysis consistent with randomization unit.

## Observational adjustment

Typically requires variants of:

- consistency,
- conditional exchangeability,
- positivity,
- valid temporal ordering,
- sufficiently correct nuisance estimation for the selected estimator.

## Difference-in-Differences

Potential requirements include:

- appropriate untreated comparison path,
- no anticipation,
- sufficient pre-treatment support,
- stable measurement / composition,
- suitable handling of staggered treatment timing.

A pre-trend test cannot prove parallel trends.

## Synthetic control

Requires a credible donor pool and adequate pre-treatment fit. Placebo analyses support interpretation but do not mechanically validate the design.

## Heterogeneity

Separate confirmatory, pre-specified subgroups from exploratory discoveries. Correct for overfitting / multiplicity where needed.

## Reporting

Unverifiable assumptions remain visible in the final report.
