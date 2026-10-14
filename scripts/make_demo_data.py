"""Generate the synthetic demo datasets (never private data).

python scripts/make_demo_data.py --out data/demo
"""

from __future__ import annotations

import argparse
from pathlib import Path

from causalimpact.simulation import ObservationalConfig, PanelConfig, RCTConfig, simulate

DEMOS = {
    "checkout_experiment": RCTConfig(n=5000, effect=0.3),
    "programme_observational": ObservationalConfig(n=3000),
    "policy_panel": PanelConfig(n_units=300),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("data/demo"))
    parser.add_argument("--seed", type=int, default=20240101)
    args = parser.parse_args()
    for name, config in DEMOS.items():
        path = simulate(config, args.seed).save(args.out / name)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
