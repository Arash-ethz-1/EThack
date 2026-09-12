"""resource_supply_risk - how exposed a company is to raw materials that are hard to get.

What it measures: for each company, the supply risk of the basket of raw materials its
industry depends on, scaled by how material-intensive that industry is. A defence
manufacturer runs on titanium, rare earths and cobalt; an asset manager runs on
almost nothing. Higher = more of the company's physical inputs come from materials
whose production is concentrated in few, badly governed countries.

Why this is environmental impact: it measures a company's claim on scarce, finite,
geographically concentrated natural resources - the abiotic depletion side of
environmental pressure, which emissions indicators miss entirely. It is also the
axis a fund can act on, because a resource a company cannot get is a resource that
stops its revenue.

    value = industry material intensity  x  weighted supply risk of its material basket

Sources:
  USGS Mineral Commodity Summaries 2026 - world production by country
  https://www.sciencebase.gov/catalog/item/696a75d5d4be0228872d3bf8
  World Bank Worldwide Governance Indicators - annual, per country
  https://databank.worldbank.org/source/worldwide-governance-indicators
  S&P 500 constituents with GICS sub-industry
  https://github.com/datasets/s-and-p-500-companies

Owner:  Jean
Run:    python run.py build environmental resource_supply_risk
Refresh cadence: quarterly. USGS republishes in January and the World Bank in
September, so a quarterly re-run picks up every upstream release within a quarter.

Output: environmental/indicators/resource_supply_risk.csv (docs/DATA_FORMAT.md)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from common.io import today_utc, write_indicator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _resource_risk import USGS_CITE, material_risk  # noqa: E402
from _universe import load_universe_with_sub_industry  # noqa: E402

CATEGORY = "environmental"
INDICATOR_ID = "resource_supply_risk"
SOURCE = "USGS Mineral Commodity Summaries 2026 + World Bank WGI"

HERE = Path(__file__).resolve().parent
BILLS_CSV = HERE / "material_bills.csv"
EXPOSURE_CSV = HERE / "subindustry_exposure.csv"

YEARS = 7


def load_bills() -> pd.DataFrame:
    """archetype -> material weights, renormalised so each basket sums to 1."""
    bills = pd.read_csv(BILLS_CSV)
    total = bills.groupby("archetype")["weight"].transform("sum")
    bills["weight"] = bills["weight"] / total
    return bills


def build() -> pd.DataFrame:
    universe, universe_note = load_universe_with_sub_industry()
    print(f"  universe: {len(universe)} companies from {universe_note}")

    bills = load_bills()
    exposure = pd.read_csv(EXPOSURE_CSV)
    risk = material_risk()

    unknown = sorted(set(bills["material"]) - set(risk["material"]))
    if unknown:
        raise ValueError(f"material_bills.csv names materials USGS does not publish: {unknown}")

    missing = sorted(set(universe["sub_industry"]) - set(exposure["sub_industry"]) - {""})
    if missing:
        raise ValueError(f"subindustry_exposure.csv is missing {len(missing)} sub-industries: {missing}")

    years = sorted(risk["year"].unique())[-YEARS:]
    risk = risk[risk["year"].isin(years)]
    print(f"  materials: {risk['material'].nunique()}  years: {years[0]}-{years[-1]}")

    # Supply risk of each archetype's basket, per year.
    basket = bills.merge(risk[["material", "year", "supply_risk"]], on="material", how="left")
    if basket["supply_risk"].isna().any():
        raise ValueError("a material in the bills has no risk score for some year")
    basket["contribution"] = basket["weight"] * basket["supply_risk"]
    basket_risk = basket.groupby(["archetype", "year"], as_index=False)["contribution"].sum()
    basket_risk = basket_risk.rename(columns={"contribution": "basket_risk"})

    companies = universe.merge(exposure, on="sub_industry", how="inner")
    rows = companies.merge(basket_risk, on="archetype", how="inner")
    rows["value"] = (rows["exposure"] * rows["basket_risk"]).round(2)

    top_material = (
        basket.sort_values("contribution", ascending=False)
        .groupby(["archetype", "year"])["material"]
        .first()
        .rename("top_material")
    )
    rows = rows.join(top_material, on=["archetype", "year"])

    rows["source"] = SOURCE
    rows["source_url"] = USGS_CITE
    rows["retrieved"] = today_utc()
    rows["note"] = (
        rows["sub_industry"]
        + " | material intensity "
        + rows["exposure"].astype(str)
        + " x basket risk "
        + rows["basket_risk"].round(1).astype(str)
        + " | largest single exposure: "
        + rows["top_material"]
    )
    return rows[["ticker", "year", "value", "source", "source_url", "retrieved", "note"]]


if __name__ == "__main__":
    df = build()
    write_indicator(CATEGORY, INDICATOR_ID, df)

    latest = df[df["year"] == df["year"].max()]
    print(f"\n  most resource-exposed companies in {int(df['year'].max())}:")
    print(latest.nlargest(10, "value")[["ticker", "value", "note"]].to_string(index=False))
    print("\n  least exposed:")
    print(latest.nsmallest(5, "value")[["ticker", "value"]].to_string(index=False))
