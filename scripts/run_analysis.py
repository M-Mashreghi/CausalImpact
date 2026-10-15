"""Run a causal study from a CSV dataset and a JSON study file.

    uv run python scripts/run_analysis.py --data examples/iran_sanctions/inflation.csv \
        --study examples/iran_sanctions/study.json --out results/iran

Prints the interpretation, estimate and any blocking problems, and writes a
reproducibility bundle (report.md, result.json, ...) to --out.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import pandas as pd

from causalimpact.services.study_file import StudyFile, run_study


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data", type=Path, required=True, help="CSV dataset")
    parser.add_argument("--study", type=Path, required=True, help="JSON study file")
    parser.add_argument("--out", type=Path, required=True, help="output bundle folder")
    args = parser.parse_args()

    study = StudyFile.model_validate_json(args.study.read_text(encoding="utf-8"))
    data = pd.read_csv(args.data, float_precision="round_trip")
    if args.out.exists():
        shutil.rmtree(args.out)
    outcome = run_study(study, data, args.out)
    if outcome.result is None:
        print("The design cannot become AnalysisReady:")
        for problem in outcome.problems:
            print(f"  - {problem}")
        return 1
    result = outcome.result
    print(result.interpretation.value)
    for reason in result.reasons:
        print(f"  - {reason}")
    if result.estimate is not None:
        e = result.estimate
        print(
            f"{e.estimand_type} = {e.estimate:.4g}  "
            f"[{e.ci_lower:.4g}, {e.ci_upper:.4g}] ({e.confidence_level:.0%})"
        )
    print(f"report: {outcome.bundle / 'report.md' if outcome.bundle else '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
