# CausalImpact Security

## Secrets and configuration

- Configuration comes from environment variables (`.env.example`); `.env` is git-ignored
  and excluded from the Docker build context (`.dockerignore`).
- No credentials are needed for mandatory CI; the workflow uses no repository secrets.
- API responses never include settings, file paths, stack traces or exception messages
  for unexpected errors; clients receive an opaque `error_id`.

## Logging

- Structured JSON logs pass through a scrubbing filter that redacts sensitive keys
  (password, secret, token, API key, authorization, cookie, credentials, DB URL/DSN),
  `key=value` secrets and bearer tokens in messages, and credentials embedded in URLs.
- Analysis logs carry identifiers, statuses and counts, never data values.

## Data

- Demo and test data are synthetic (`causalimpact.simulation`); no private data is
  bundled into images or repositories (`data/` is excluded from Docker builds and
  ignored by git except fixtures).
- Reproducibility bundles contain the analysis dataset; treat them with the same data
  classification as the source data.

## Dependencies

- Versions are locked in `uv.lock`; the container installs `requirements.lock` with
  `--require-hashes`. CI checks both locks are current.
- CI runs `pip-audit --strict` against `requirements.lock` on every push and pull request.
  A known vulnerability blocks the merge until the dependency is upgraded or the advisory
  is assessed and documented in the release notes.
- New runtime dependencies require task-level justification (CLAUDE.md, "Dependencies").

## Container

- The image runs as an unprivileged user (uid 10001), exposes only 8000/8501 and has a
  health check. The registry lives on a named volume.

## Reporting a vulnerability

Open a private security advisory on the GitHub repository rather than a public issue.
