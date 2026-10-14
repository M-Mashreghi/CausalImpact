"""Run the three demo analyses, export bundles and verify they re-run (release evidence).

python scripts/demo_release.py --out artifacts/demo_release
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from causalimpact.domain import TreatmentSpec
from causalimpact.services.estimator_factory import (
    AIPWConfig,
    DifferenceInMeansConfig,
    SingleCohortDiDConfig,
)
from causalimpact.services.registry import export_bundle, rerun_bundle
from causalimpact.services.run_spec import DiagnosticsConfig, RunSpec, execute

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.integration.scenarios import X, observational, panel_policy, rct

EXPERIMENT = {
    "experiment_id": "checkout",
    "arms": [{"name": "control", "allocation": 0.5}, {"name": "treatment", "allocation": 0.5}],
    "control_arm": "control",
    "randomization_unit": "user_id",
    "analysis_unit": "user_id",
    "primary_metric": "revenue",
}
DEMOS = {
    "checkout_experiment": (
        rct,
        RunSpec(
            estimator=DifferenceInMeansConfig(
                treatment=TreatmentSpec(
                    name="arm", control_value="control", treated_value="treatment"
                )
            ),
            diagnostics=DiagnosticsConfig.model_validate({"experiment": EXPERIMENT}),
            seed=1,
        ),
    ),
    "programme_observational": (
        observational,
        RunSpec(
            estimator=AIPWConfig(treatment=TreatmentSpec(name="treated"), covariates=(X,)), seed=2
        ),
    ),
    "policy_panel": (panel_policy, RunSpec(estimator=SingleCohortDiDConfig(), seed=3)),
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/demo_release"))
    parser.add_argument("--seed", type=int, default=20240101)
    args = parser.parse_args()
    summary = {}
    for name, (make, spec) in DEMOS.items():
        scenario = make(np.random.default_rng(args.seed))
        result = execute(scenario.service, scenario.design, spec, scenario.data)
        bundle = export_bundle(result, spec, scenario.data, scenario.service, args.out / name)
        check = rerun_bundle(bundle)
        est = result.estimate
        summary[name] = {
            "interpretation": result.interpretation.value,
            "estimand": result.estimand.type.value,
            "estimate": None if est is None else round(est.estimate, 4),
            "ci": None if est is None else [round(est.ci_lower, 4), round(est.ci_upper, 4)],
            "run_fingerprint": result.run_fingerprint,
            "dataset_version": result.run.dataset_version,
            "reproduced": check.reproduced,
        }
    print(json.dumps(summary, indent=2))
    return 0 if all(v["reproduced"] for v in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
