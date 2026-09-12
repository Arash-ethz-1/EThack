"""critical_material_disclosure - critical-material dependence a company states itself.

What it measures: the combined supply risk of the raw materials a company names in
its own 10-K that year, scaled to [0,1] where 1 is the theoretical ceiling - naming
every one of the 23 tracked critical materials, each at maximum possible risk. A
company that tells investors it depends on rare earths, cobalt and gallium scores
high; one that names only copper scores low.

Why this is different from `resource_supply_risk`: that indicator assigns every
company in a sub-industry the same score, because it works from an industry material
bill. This one reads each company's own statutory filing, so two semiconductor
companies can differ, and one company can change from year to year. The cost is
coverage - it can only score companies that name a material at all.

Why this is environmental impact: a company's own disclosure of dependence on scarce,
concentrated minerals is the most direct evidence available that its operations draw
on finite natural resources under strain.

Sources:
  SEC EDGAR full-text search over 10-K filings (statutory disclosure, 2001-present)
  https://efts.sec.gov/LATEST/search-index
  Material supply risk from USGS Mineral Commodity Summaries 2026 + World Bank WGI
  (see _resource_risk.py)

Owner:  Jean
Run:    python run.py build environmental critical_material_disclosure
Refresh cadence: quarterly - 10-Ks are filed all year, so new filings appear
continuously and a quarterly re-run picks them up.

Output: environmental/indicators/critical_material_disclosure.csv (docs/DATA_FORMAT.md)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from common.io import today_utc, write_indicator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _edgar_materials import TERM_TO_MATERIAL, filing_url, mentions  # noqa: E402
from _resource_risk import material_risk  # noqa: E402
from _universe import load_universe_with_sub_industry  # noqa: E402

CATEGORY = "environmental"
INDICATOR_ID = "critical_material_disclosure"
SOURCE = "SEC EDGAR 10-K full-text search"

YEARS = 7


def build() -> pd.DataFrame:
    universe, universe_note = load_universe_with_sub_industry()
    print(f"  universe: {len(universe)} companies from {universe_note}")

    risk = material_risk()
    years = sorted(risk["year"].unique())[-YEARS:]
    by_material = risk.set_index(["material", "year"])["supply_risk"]

    # A 10-K filed in year Y almost always reports the year before, so search one
    # filing year past the window and let period_ending decide which year a row is.
    cik_to_ticker = dict(zip(universe["cik"], universe["ticker"]))
    found = mentions(list(range(years[0] + 1, years[-1] + 2)), set(cik_to_ticker), refresh=False)

    df = pd.DataFrame(found)
    df = df[df["year"].isin(years)]
    df = df.drop_duplicates(subset=["cik", "year", "material"])
    df["supply_risk"] = [
        by_material.get((m, y), float("nan")) for m, y in zip(df["material"], df["year"])
    ]
    df = df[df["supply_risk"].notna()]

    agg = df.groupby(["cik", "year"]).agg(
        value=("supply_risk", "sum"),
        n_materials=("material", "nunique"),
        materials=("material", lambda s: ", ".join(sorted(set(s)))),
        adsh=("adsh", "first"),
    ).reset_index()

    agg["ticker"] = agg["cik"].map(cik_to_ticker)
    agg = agg[agg["ticker"].notna()]
    # Raw value is a sum of per-material risk (0-100 each) over however many of the
    # tracked materials a company names, so it has no natural ceiling per company.
    # Divide by the maximum any company could reach - every tracked material named,
    # each at the worst possible risk - for a stable [0,1] index that does not shift
    # as new companies or years change the observed range.
    max_possible = len(set(TERM_TO_MATERIAL.values())) * 100
    agg["value"] = (agg["value"] / max_possible).round(4)
    agg["source"] = SOURCE
    agg["source_url"] = [
        filing_url(c, a) if a else "https://efts.sec.gov/LATEST/search-index"
        for c, a in zip(agg["cik"], agg["adsh"])
    ]
    agg["retrieved"] = today_utc()
    agg["note"] = agg["n_materials"].astype(str) + " materials named in the 10-K: " + agg["materials"]

    latest = agg[agg["year"] == years[-1]]
    print(
        f"  coverage: {latest['ticker'].nunique()}/{len(universe)} companies named "
        f"a critical material in their {years[-1]} 10-K"
    )
    return agg[["ticker", "year", "value", "source", "source_url", "retrieved", "note"]]


if __name__ == "__main__":
    df = build()
    write_indicator(CATEGORY, INDICATOR_ID, df)

    latest = df[df["year"] == df["year"].max()]
    print(f"\n  most exposed by their own disclosure in {int(df['year'].max())}:")
    print(latest.nlargest(12, "value")[["ticker", "value", "note"]].to_string(index=False))
