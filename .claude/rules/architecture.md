# Architecture Rules

Canonical flow:

```text
Data → Validation → Design → Estimand → Identification → Estimator → Diagnostics → Sensitivity → Report
```

- Keep design logic separate from estimator implementations.
- Keep diagnostics independent from reporting.
- UI calls services; it does not calculate causal estimates.
- External causal libraries must be wrapped behind project contracts.
