# Example: the 2012 sanctions tightening and inflation in Iran

**Question.** How much did the 2012 tightening of international sanctions on Iran (EU oil
embargo and central-bank sanctions) change Iran's annual CPI inflation in 2012–2015?

This is a single-treated-unit macro question, so the design is a **synthetic control**:
a weighted combination of other countries chosen to reproduce Iran's inflation in
1996–2011, used as the counterfactual for 2012–2015. It cannot answer "is Iran's
inflation *always* caused by sanctions": inflation was high before these sanctions and
has other drivers (oil revenue, fiscal deficits, monetary policy, the late-2010 subsidy
reform). It estimates the effect of one sanctions episode, under stated assumptions.

## Run it

```bash
uv run python examples/iran_sanctions/fetch_data.py      # optional: re-download World Bank data
uv run python examples/iran_sanctions/prepare_panel.py   # build inflation.csv (declared donor rule)
uv run python scripts/run_analysis.py \
    --data examples/iran_sanctions/inflation.csv \
    --study examples/iran_sanctions/study.json \
    --out artifacts/iran_sanctions
```

The full report is written to `artifacts/iran_sanctions/report.md`; open the same folder
in the diagnostics dashboard to inspect it.

## Files

| File | Contents |
|---|---|
| `fetch_data.py` | downloads World Bank WDI `FP.CPI.TOTL.ZG` (CPI inflation, annual %), CC BY 4.0 |
| `inflation_raw.csv` | the downloaded data (1990–2019, all countries) |
| `prepare_panel.py` | window 1996–2015, treatment 2012, declared donor-pool rule |
| `inflation.csv` | analysis panel: Iran + 141 donor countries |
| `study.json` | estimand, design, assumption justifications, estimator and placebo settings |

Donor-pool rule (declared before looking at results): complete data for 1996–2015, no
comprehensive sanctions or major war in the window, no year above 100% inflation.

## Result (as produced by the tool)

**Interpretation: Suggestive; important diagnostics/assumptions unresolved.**

| Quantity | Value |
|---|---|
| Estimated effect (ATT, 2012–2015 average) | **+13.6 percentage points** of annual inflation |
| Placebo-based 95% interval | [9.2, 18.1] |
| Placebo rank p-value | 0.155 (Iran ranks 22 of 142 by post/pre RMSPE ratio) |
| Synthetic Iran | mainly Ethiopia (0.43) and Zambia (0.42), plus Turkey, Nigeria, Serbia, Mongolia |
| Iran vs synthetic, 2012 / 2013 / 2014 / 2015 | 27.3 vs 14.4 / 36.6 vs 7.4 / 16.6 vs 7.4 / 12.5 vs 9.3 |

Why the tool does **not** call this a supported causal estimate:

1. **Mediocre pre-treatment fit** (pre-RMSPE is 0.55× Iran's pre-period SD). In 2011,
   before the treatment year, Iran was already at 26.3% vs 18.3% for the synthetic unit,
   consistent with the late-2010 subsidy reform and with anticipation of sanctions.
2. **Not extreme among placebos.** 21 untreated countries show a larger post/pre
   divergence than Iran, so p = 0.155. The placebo-quantile interval excludes zero, but
   the rank test, which accounts for fit quality, does not reject.
3. **In-time placebo flagged.** A fake treatment in 2007 already produces a 7.2-point gap.
   That period itself saw UN Security Council sanctions (2006–2008), so it is not a clean
   placebo, but it shows that Iran's inflation diverges from the comparison group at other
   times too.

**Reading.** The data are consistent with sanctions raising Iranian inflation sharply in
2012–2013, but this design cannot separate that from other shocks of the same period
(subsidy reform, exchange-rate policy) with the confidence needed for a causal claim.
Stronger evidence would need monthly data, covariates (oil revenue, money growth,
exchange rates), a donor pool justified economically, and sensitivity to the donor rule.
