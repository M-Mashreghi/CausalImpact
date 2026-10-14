# CausalImpact Release Checklist

Copy this list into `docs/releases/<version>.md` and record evidence for every item.
A release is blocked if any item cannot be ticked (DEPLOYMENT.md, "Release blockers").

## Quality gates
- [ ] CI `ci-gate` is green on the release commit (lint, types, tests, simulation suite).
- [ ] Research gates artifact attached: known-truth bias and coverage pass for every
      reference estimator; every failure mode detected; controls quiet.
- [ ] No material bias/coverage regression versus the previous release's artifact.
- [ ] Container smoke test passed (`/health`, `/ready`, dashboard health).

## Security
- [ ] `pip-audit --strict` clean, or every advisory assessed and documented.
- [ ] `uv.lock` and `requirements.lock` current; no new unjustified dependencies.
- [ ] No secrets in the repository or image; logs scrubbed (observability tests green).

## Reproducibility
- [ ] Every analysis in the release notes has a bundle that re-runs with
      `reproduced = True` (same fingerprint, estimate and interpretation).
- [ ] Dataset versions, design/DAG/adjustment-set versions, seeds and code version are
      recorded in each run.
- [ ] Demo datasets regenerate byte-identically from their seed.

## Model risk
- [ ] Estimand stated before the estimator in every reported analysis; no silent
      estimand or population change (derived estimands for trimming and subgroups).
- [ ] Required diagnostics ran; blocked analyses are reported as "Causal interpretation
      not supported", never with an estimate.
- [ ] Untestable assumptions listed in every report; no assumption reported as proven.
- [ ] Deferred (Advanced) capabilities are not claimed in documentation or reports.
- [ ] Known limitations and invalidated runs since the last release are listed.
