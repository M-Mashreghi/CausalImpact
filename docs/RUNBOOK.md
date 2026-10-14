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

## Operations

### Start / stop

```bash
docker compose up -d --build        # API :8000, dashboard :8501
docker compose down                 # keeps the registry volume
docker compose down -v              # also deletes the registry volume (destructive)
```

Without Docker: `uv run uvicorn --factory causalimpact.api.server:build_app` and
`uv run streamlit run src/causalimpact/dashboard/diagnostics_app.py`.

### Health

- `GET /health`: liveness (process up).
- `GET /ready`: readiness; `503` with `{"components": {"registry": "unavailable"}}` means
  the SQLite registry cannot be opened. Check the volume / `CAUSALIMPACT_DB_URL` path and
  file permissions. The endpoint never returns configuration values.

### Logs

Logs are one JSON object per line on stderr (`docker compose logs api`). Every analysis
emits `analysis_run_started` and `analysis_run_finished` with the run id, status,
interpretation and blocked diagnostics. Unexpected API errors are logged as
`unhandled_error` with an `error_id` that matches the id returned to the client. Secrets,
credentials and connection strings are redacted before logs are written; data values are
never logged.

### Backup and recovery

The registry is a single SQLite file (`/app/var/causalimpact.db` in the container).

```bash
docker compose exec api python -c "import sqlite3; s=sqlite3.connect('/app/var/causalimpact.db'); d=sqlite3.connect('/app/var/backup.db'); s.backup(d)"
docker compose cp api:/app/var/backup.db ./backup-$(date +%F).db
```

To recover, stop the stack, copy the backup into the volume as `causalimpact.db` and
start again; `GET /ready` must report `registry: ok`. Reproducibility bundles
(`export_bundle`) are self-contained and can be re-run on any machine with
`rerun_bundle` regardless of the registry.

### Invalidating results

When a bug affects prior estimates, never delete or edit runs:

```bash
python scripts/invalidate_run.py --db var/causalimpact.db --run run_<id> --reason "<bug and fix commit>"
python scripts/invalidate_run.py --db var/causalimpact.db --all --run sha256:<fingerprint> --reason "..."
```

The original result stays in the registry; `AnalysisRegistry.runs()` and the API report
the invalidation and its reason. Re-run affected specifications from their bundles after
the fix and compare.
