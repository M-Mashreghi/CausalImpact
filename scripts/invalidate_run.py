"""Mark an AnalysisRun invalidated in the registry (history is kept, never overwritten).

python scripts/invalidate_run.py --db var/causalimpact.db --run run_<id> --reason "..."
"""

from __future__ import annotations

import argparse

from causalimpact.services.registry import AnalysisRegistry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--run", required=True, help="run id, or a fingerprint with --all")
    parser.add_argument("--reason", required=True)
    parser.add_argument(
        "--all", action="store_true", help="invalidate every run sharing this fingerprint"
    )
    args = parser.parse_args()
    registry = AnalysisRegistry(args.db)
    if args.all:
        targets = [r.run_id for r in registry.runs() if r.fingerprint == args.run]
    else:
        targets = [args.run]
    for run_id in targets:
        registry.invalidate(run_id, args.reason)
        print(f"invalidated {run_id}")


if __name__ == "__main__":
    main()
