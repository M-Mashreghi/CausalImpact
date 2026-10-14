# Sequential Experimentation Rules

- Fixed-horizon p-values must not be repeatedly monitored and interpreted as if only one test occurred.
- If continuous monitoring is implemented, use an explicit sequential design (e.g. alpha spending, always-valid/e-process style design, or approved group-sequential method).
- Record planned horizon, stopping rule, and monitoring policy.
- Do not add sequential inference to v1 estimators implicitly; it is a separate capability.
