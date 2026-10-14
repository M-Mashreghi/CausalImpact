# CausalImpact Deployment

## Local development

Python 3.12 is the pinned baseline (`.python-version`); dependency versions are locked in `uv.lock`.

```bash
uv sync --extra dev          # or: python -m venv .venv && pip install -e ".[dev]"
uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```

## Environment

```env
CAUSALIMPACT_ENV=development
CAUSALIMPACT_DB_URL=sqlite:///./data/causalimpact.db
```

## CI quality gates

- lint / type checks,
- unit + integration tests,
- simulation smoke benchmarks,
- causal-regression gates (coverage/bias/failure-mode fixtures),
- dependency security audit,
- docs consistency check.

## Release blockers

Do not release when known-effect benchmarks regress materially, critical diagnostics silently disappear, secrets are present, or mandatory tests fail.
