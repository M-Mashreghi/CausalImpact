"""Build the analysis panel from inflation_raw.csv (declared, fixed donor-pool rule).

Window 1996-2015: pre-treatment 1996-2011, treatment 2012 (EU oil embargo and
central-bank sanctions), post 2012-2015 (before the 2016 JCPOA relief).

Donor pool rule, declared before looking at results:
  * complete annual CPI inflation for every year 1996-2015;
  * not under comprehensive sanctions or major war in the window (excluded below);
  * no hyperinflation (> 100% in any year), which would dominate the fit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
TREATED, START, FIRST, LAST = "IRN", 2012, 1996, 2015
SANCTIONED_OR_WAR = {
    "AFG", "CUB", "IRQ", "LBY", "MMR", "PRK", "RUS", "SDN", "SOM", "SSD", "SYR", "VEN",
    "YEM", "ZWE", "BLR", "UKR",
}  # fmt: skip


def main() -> None:
    raw = pd.read_csv(HERE / "inflation_raw.csv")
    wide = raw.pivot(index="iso3", columns="year", values="inflation")  # noqa: PD010
    wide = wide.loc[:, FIRST:LAST].dropna()
    hyper = wide.index[(wide > 100).any(axis=1)]
    donors = [u for u in wide.index if u != TREATED and u not in SANCTIONED_OR_WAR | set(hyper)]
    long = (
        wide.loc[[TREATED, *donors]]
        .reset_index()
        .melt(id_vars="iso3", var_name="period", value_name="outcome")
        .rename(columns={"iso3": "unit_id"})
    )
    long["treatment_start"] = long["unit_id"].map({TREATED: float(START)})
    long = long.sort_values(["unit_id", "period"])[
        ["unit_id", "period", "treatment_start", "outcome"]
    ]
    long.to_csv(HERE / "inflation.csv", index=False, lineterminator="\n")
    print(f"{len(donors)} donors, {long.shape[0]} rows -> inflation.csv")


if __name__ == "__main__":
    main()
