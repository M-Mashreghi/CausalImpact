# Quickstart: try CausalImpact locally

Windows PowerShell, from the project folder (`D:\Github Projects\CausalImpact`). Requires
[uv](https://docs.astral.sh/uv/); it installs Python 3.12 and the locked dependencies.

```powershell
cd "D:\Github Projects\CausalImpact"
git pull
uv sync --extra dev
```

## 1. Run the tests

```powershell
uv run pytest -m "not simulation" -n 6        # fast suite (~1 min)
uv run pytest -n 6                              # everything, incl. simulations (~2-4 min)
```

## 2. Run the three demo analyses

```powershell
uv run python scripts/demo_release.py
```

Runs a randomized experiment (ITT), an observational study (AIPW, ATE) and a policy
panel (DiD, ATT) on synthetic data with known effects, prints the estimate, interval and
interpretation for each, and writes a reproducibility bundle per analysis to
`artifacts\demo_release\<name>\`. Open `report.md` in any bundle to read the full
assumption-aware report.

## 3. Diagnostics dashboard

```powershell
uv run streamlit run src/causalimpact/dashboard/diagnostics_app.py
```

Opens http://localhost:8501. Paste the path of a result, for example
`D:\Github Projects\CausalImpact\artifacts\demo_release\checkout_experiment\result.json`.

## 4. Study designer

```powershell
uv run streamlit run src/causalimpact/dashboard/designer_app.py
```

Fill in a design; it is only promoted to AnalysisReady when every required field and
justified assumption is present. Try leaving a field empty to see the blocking problems.

## 5. HTTP API

```powershell
uv run uvicorn --factory causalimpact.api.server:build_app
```

Opens http://127.0.0.1:8000. Interactive documentation: http://127.0.0.1:8000/docs.
Health: `/health`, readiness: `/ready`. Results persist in `data\causalimpact.db`.

Stop any server with `Ctrl+C`.
