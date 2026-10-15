"""Download annual CPI inflation (World Bank WDI, FP.CPI.TOTL.ZG) for all countries.

Public data, licensed CC BY 4.0 by the World Bank. Writes inflation_raw.csv with columns
iso3, country, year, inflation. Run from the repository root:

    uv run python examples/iran_sanctions/fetch_data.py
"""

from __future__ import annotations

import csv
import json
import urllib.request
from pathlib import Path

API = "https://api.worldbank.org/v2"
OUT = Path(__file__).with_name("inflation_raw.csv")


def get(url: str) -> list[dict[str, object]]:
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload[1] or []


def main() -> None:
    countries = {
        c["id"]: c["name"]
        for c in get(f"{API}/country?format=json&per_page=400")
        if c["region"]["value"] != "Aggregates"  # type: ignore[index]
    }
    rows = get(
        f"{API}/country/all/indicator/FP.CPI.TOTL.ZG?format=json&date=1990:2019&per_page=20000"
    )
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["iso3", "country", "year", "inflation"])
        for r in rows:
            iso3 = r["countryiso3code"]
            if iso3 in countries and r["value"] is not None:
                writer.writerow([iso3, countries[iso3], r["date"], r["value"]])
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
