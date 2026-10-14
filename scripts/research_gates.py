"""Causal-regression research gates for CI (Task 8.4).

Runs a fixed, seeded set of known-truth benchmarks and the failure-mode suite, writes a
JSON artifact, and exits non-zero if any gate fails:

* bias within tolerance (absolute tolerance + 4 Monte Carlo SE) for reference estimators;
* CI coverage not severely below nominal and failure rate low;
* every injected failure mode detected (>= 0.9) and clean controls quiet (<= 0.25).

    python scripts/research_gates.py --out artifacts/research_gates.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from causalimpact.domain import (
    CovariateDType,
    CovariateSpec,
    Estimand,
    EstimandType,
    TargetPopulation,
    TreatmentBasis,
    TreatmentSpec,
    TriState,
)
from causalimpact.estimators import Estimator
from causalimpact.experiments.estimators import DifferenceInMeans
from causalimpact.observational.aipw import AIPWEstimator
from causalimpact.panel.contract import PanelSpec
from causalimpact.panel.did import TwoPeriodDiD
from causalimpact.simulation import (
    BenchmarkCase,
    ObservationalConfig,
    PanelConfig,
    RCTConfig,
    bias_within_tolerance,
    check_coverage,
    coverage_summary,
    run_benchmark,
    run_failure_mode_suite,
)

POP = TargetPopulation(name="simulated", description="simulated units")
X = CovariateSpec(
    name="x",
    dtype=CovariateDType.NUMERIC,
    measurement_time="baseline",
    pre_treatment=TriState.TRUE,
    descendant_of_treatment=TriState.FALSE,
)


def _estimand(kind: EstimandType, treatment: str, outcome: str) -> Estimand:
    return Estimand(
        estimand_id=f"{kind.value.lower()}_{outcome}",
        type=kind,
        treatment=treatment,
        outcome=outcome,
        target_population=POP,
        treatment_basis=TreatmentBasis.ASSIGNMENT
        if kind is EstimandType.ITT
        else TreatmentBasis.RECEIPT,
    )


def _dim(_: int) -> Estimator:
    return DifferenceInMeans(
        TreatmentSpec(name="arm", control_value="control", treated_value="treatment")
    )


def _aipw(_: int) -> Estimator:
    return AIPWEstimator(TreatmentSpec(name="treated"), (X,))


def _did(_: int) -> Estimator:
    return TwoPeriodDiD(PanelSpec(), pre_period=1, post_period=2)


CASES = (
    (BenchmarkCase("rct_difference_in_means", RCTConfig(n=1000), _dim,
                   _estimand(EstimandType.ITT, "arm", "y"), "ITT"), 0.02),
    (BenchmarkCase("observational_aipw", ObservationalConfig(n=2000), _aipw,
                   _estimand(EstimandType.ATE, "treated", "y"), "ATE"), 0.05),
    (BenchmarkCase("panel_did_2x2",
                   PanelConfig(n_units=300, n_periods=2, cohorts=(2,), dynamic_effects=(1.5,)),
                   _did, _estimand(EstimandType.ATT, "treatment_start", "outcome"),
                   "ATT_post_average"), 0.05),
)  # fmt: skip


def run(replicates: int, seed: int) -> dict[str, object]:
    gates: list[dict[str, object]] = []
    for case, tolerance in CASES:
        result = run_benchmark(case, n_replicates=replicates, seed=seed)
        cov = coverage_summary(result)
        gate = check_coverage(cov)
        gates.append(
            {
                "case": case.name,
                "bias": result.bias,
                "bias_mc_se": result.bias_mc_se,
                "rmse": result.rmse,
                "coverage": cov.coverage,
                "failure_rate": result.failure_rate,
                "bias_ok": bias_within_tolerance(result, abs_tol=tolerance),
                "coverage_ok": not gate.is_blocking,
                "coverage_findings": sorted(gate.codes()),
            }
        )
    failure_modes = run_failure_mode_suite(seed=seed, n_replicates=8)
    detection: list[dict[str, object]] = []
    for s in failure_modes.scenarios:
        if s.detection_rate is None:
            ok = True  # demonstration-only scenario (detector deferred to Task 2.12)
        elif s.failure_injected:
            ok = s.detection_rate >= 0.9
        else:
            ok = s.detection_rate <= 0.25
        detection.append({"scenario": s.name, "detection_rate": s.detection_rate, "ok": ok})
    passed = all(g["bias_ok"] and g["coverage_ok"] for g in gates) and all(
        d["ok"] for d in detection
    )
    return {"passed": passed, "seed": seed, "replicates": replicates,
            "benchmarks": gates, "failure_modes": detection}  # fmt: skip


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/research_gates.json"))
    parser.add_argument("--replicates", type=int, default=200)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    report = run(args.replicates, args.seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
