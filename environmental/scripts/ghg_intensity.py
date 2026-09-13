"""ghg_intensity - direct US greenhouse gas emissions per $M of revenue.

What it measures: the Scope 1 CO2e emitted by a company's large US facilities - every
facility above 25,000 tCO2e/yr must report to EPA's Greenhouse Gas Reporting Program
(GHGRP, 40 CFR Part 98: power plants, refineries, cement/steel/chemical plants, landfills,
pipelines ...) - split across owners by the ownership share GHGRP itself records, divided
by that year's revenue. Lower is better: less climate damage per dollar the company earns.
Size-neutral by construction.

Every company with revenue gets a value. A company with no matched GHGRP facility gets 0
with a note: its direct US emissions are below the reporting threshold (typical for
software, banks, retail) - an observation from EPA's complete facility list, not "zero
emissions". Rank it within a sector (sector_relative profiles): a bank is not compared
with a steel maker. Hand-checked: in Utilities 30/31, Energy 17/20 and Materials 20/25
companies have facilities (2023); the zeros there (AWK, BKR, SLB, TPL, AVY, BALL, ECL,
SHW, VMC) are service, packaging, coatings and aggregates firms without a >=25 kt plant.

Method:
  1. EPA Envirofacts GHGRP: RLPS_GHG_EMITTER_GAS (facility x year x gas -> co2e, summed
     per facility-year) joined with PUB_DIM_FACILITY `parent_company` ("EXXON MOBIL CORP
     (100%)", or several owners with a % each - EPA's own reported split).
  2. Owner names -> S&P 500 parent (match_owners): social/scripts/_company_match.py
     (current/former SEC names, 10-K Exhibit 21 subsidiaries), then the whole-word rule on
     the normalised S&P 500 name (also with spaces removed, "EXXONMOBIL" = "EXXON MOBIL";
     names under 6 letters only as the whole owner name, "AES CORP"; GENERIC_NAMES exact
     only); government/municipal owners never. Spin-off collisions (Howmet vs Alcoa Corp /
     Arconic Corp) are blocked. Every match: environmental/raw/ghg_intensity_matches.csv.
  3. Revenue: environmental/scripts/_revenue.py (SEC XBRL, fiscal year = year the period
     ends; companyfacts fallback, e.g. XOM under its pre-2026 CIK).
  4. value = attributed tCO2e / revenue in $M. Raw numbers: ghg_intensity_raw_ratio.csv.

Changed 2026-09-13 (Arash): the value was a percentile rank among only the ~95 matched
companies and dropped every company whose revenue lookup used SEC's `fy` field (XEL, DTE
...). Now the raw ratio for all companies, so common/score.py ranks it like every other
indicator.

Limits: US facilities only (foreign plants invisible), Scope 1 only, facilities below the
threshold invisible, asset managers are listed as parents of fund-owned plants (ARES, BX).
No 2024/2025 rows: GHGRP publishes year Y in autumn of Y+1; missing years are not filled.

Sources:
  EPA Envirofacts GHGRP API (facility emissions + reported ownership)
  https://data.epa.gov/efservice/RLPS_GHG_EMITTER_GAS
  https://data.epa.gov/efservice/PUB_DIM_FACILITY
  SEC EDGAR XBRL companyconcept (annual revenue)
  https://data.sec.gov/api/xbrl/companyconcept/

Owner:  Jean (method reworked by Arash 2026-09-13)
Run:    python run.py build environmental ghg_intensity
Refresh cadence: annual - GHGRP publishes year Y data in autumn of Y+1.

Output: environmental/indicators/ghg_intensity.csv (docs/DATA_FORMAT.md)
Also writes environmental/raw/ghg_intensity_matches.csv (every owner-name match, for
spot-checking) and environmental/raw/ghg_intensity_raw_ratio.csv (the raw tCO2e per
$M revenue ratio behind each percentile, for anyone who wants the un-rescaled number).
"""

from __future__ import annotations

import re

import pandas as pd

from common.io import cached_json, http_headers, load_universe, today_utc, write_indicator
from common.config import raw_dir
import requests
import time

CATEGORY = "environmental"
INDICATOR_ID = "ghg_intensity"
SOURCE = "EPA GHGRP (Envirofacts) + SEC XBRL revenue"
EPA_BASE = "https://data.epa.gov/efservice"
YEARS = list(range(2018, 2026))  # trimmed to years EPA has actually published, see build()
PAGE_SIZE = 5000

MATCHES_PATH = raw_dir(CATEGORY) / "ghg_intensity_matches.csv"
RAW_RATIO_PATH = raw_dir(CATEGORY) / "ghg_intensity_raw_ratio.csv"

SUFFIX_RE = re.compile(
    r"\b(INCORPORATED|CORPORATION|COMPANY|HOLDINGS?|GROUP|LLC|LLP|LP|PLC|LTD|CORP|CO|INC|THE)\b"
)
PUNCT_RE = re.compile(r"[^A-Z0-9 ]")
PCT_RE = re.compile(r"^(.*?)\(([\d.]+)\s*%\)\s*$")

# Common English/geographic words or generic industry phrases that survive
# normalisation as a company's whole name (e.g. "Southern Co" -> "SOUTHERN", "Waste
# Management, Inc." -> "WASTE MANAGEMENT") but also occur as, or inside, unrelated
# entities' names (e.g. "Southern California Public Power Authority", "Broome
# County Div of Solid Waste Management") - a name in this set must match the owner
# text exactly, never as a substring/prefix, or a facility gets attributed to the
# wrong company. Found by hand-checking the 2018-23 GHGRP match log (AGENTS.md rule
# 6); extended defensively with names in the same category not yet seen.
GENERIC_NAMES = {
    "SOUTHERN", "NORTHERN", "EASTERN", "WESTERN", "CENTRAL", "NATIONAL", "GENERAL",
    "AMERICAN", "UNITED", "FIRST", "PUBLIC", "FEDERAL", "STATE", "MUNICIPAL",
    "REGIONAL", "GLOBAL", "TARGET", "WATERS", "AUTHORITY", "DISTRICT", "COUNTY",
    "PROGRESSIVE", "WASTE MANAGEMENT", "CORNING",
}

# Government/municipal bodies (county solid-waste districts, city utilities, water
# authorities, ...) routinely use ordinary business words in their own names ("Waste
# Management", "Southern", "Electric Cooperative") without being related to any
# S&P 500 company - a facility owner containing one of these markers is skipped
# entirely rather than matched, since no S&P 500 company's own legal/subsidiary name
# contains them (found the same way, via the match log: e.g. "Old Dominion Electric
# Cooperative" wrongly matching Old Dominion Freight Line (ODFL), "Cumberland County
# Solid Waste Management" wrongly matching Waste Management Inc (WM)).
GOVERNMENT_ENTITY_RE = re.compile(
    r"\b(CITY OF|COUNTY|TOWNSHIP|TOWN OF|VILLAGE OF|STATE OF|AUTHORITY|DISTRICT|"
    r"MUNICIPAL|COOPERATIVE|COMMISSION|BOARD OF|AGENCY|DEPARTMENT|DEPT OF|DIV OF|"
    r"PUBLIC WORKS)\b"
)


def normalise(name: str) -> str:
    name = PUNCT_RE.sub(" ", name.upper())
    name = SUFFIX_RE.sub(" ", name)
    return " ".join(name.split())


def parse_owners(parent_company: str) -> list[tuple[str, float]]:
    """'A (74.3%); B (14%); C' -> [(A, 0.743), (B, 0.14), (C, 1.0)]."""
    if not parent_company or not isinstance(parent_company, str):
        return []
    owners = []
    for part in parent_company.split(";"):
        part = part.strip()
        if not part:
            continue
        m = PCT_RE.match(part)
        if m:
            owners.append((m.group(1).strip(), float(m.group(2)) / 100.0))
        else:
            owners.append((part, 1.0))
    return owners


def fetch_epa_table(table: str, year: int) -> pd.DataFrame:
    rows = []
    start = 0
    while True:
        fname = f"{table.lower()}_{year}_{start}.json"
        try:
            data = cached_json(
                f"{EPA_BASE}/{table}/YEAR/{year}/ROWS/{start}:{start + PAGE_SIZE - 1}/JSON",
                CATEGORY,
                fname,
            )
        except requests.HTTPError:
            break
        if not isinstance(data, list) or not data or "error" in data[0]:
            break
        rows.extend(data)
        if len(data) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return pd.DataFrame(rows)


def available_years() -> list[int]:
    years = []
    for y in YEARS:
        r = requests.get(f"{EPA_BASE}/RLPS_GHG_EMITTER_GAS/YEAR/{y}/COUNT/JSON", headers=http_headers(), timeout=30)
        r.raise_for_status()
        n = r.json()[0]["TOTALQUERYRESULTS"]
        if n > 0:
            years.append(y)
        time.sleep(0.1)
    return years


def facility_totals(year: int) -> pd.DataFrame:
    gas = fetch_epa_table("RLPS_GHG_EMITTER_GAS", year)
    if gas.empty:
        return pd.DataFrame(columns=["facility_id", "co2e_tonnes"])
    return gas.groupby("facility_id", as_index=False)["co2e_emission"].sum().rename(
        columns={"co2e_emission": "co2e_tonnes"}
    )


def facility_parents(year: int) -> pd.DataFrame:
    fac = fetch_epa_table("PUB_DIM_FACILITY", year)
    if fac.empty:
        return pd.DataFrame(columns=["facility_id", "parent_company"])
    fac = fac.dropna(subset=["parent_company"])
    return fac.drop_duplicates(subset=["facility_id"])[["facility_id", "parent_company"]]


def match_year(year: int, name_index: dict[str, str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (ticker-year attributed co2e, match log rows)."""
    totals = facility_totals(year)
    parents = facility_parents(year)
    joined = totals.merge(parents, on="facility_id", how="inner")

    attributed: dict[str, float] = {}
    matches = []
    for _, row in joined.iterrows():
        for owner_name, share in parse_owners(row["parent_company"]):
            norm = normalise(owner_name)
            if GOVERNMENT_ENTITY_RE.search(norm):
                continue  # a government/municipal body, never an S&P 500 company
            for sp500_norm, ticker in name_index.items():
                if len(sp500_norm) < 6:
                    continue
                is_match = (
                    norm == sp500_norm
                    if sp500_norm in GENERIC_NAMES
                    else bool(re.search(rf"\b{re.escape(sp500_norm)}\b", norm))
                )
                if is_match:
                    co2e = row["co2e_tonnes"] * share
                    attributed[ticker] = attributed.get(ticker, 0.0) + co2e
                    matches.append(
                        {
                            "year": year,
                            "ticker": ticker,
                            "facility_id": row["facility_id"],
                            "parent_company_raw": row["parent_company"],
                            "owner_segment": owner_name,
                            "share": share,
                            "facility_co2e_tonnes": row["co2e_tonnes"],
                            "attributed_co2e_tonnes": co2e,
                        }
                    )
                    break  # one ticker per owner segment

    result = pd.DataFrame(
        [{"ticker": t, "year": year, "co2e_tonnes": v} for t, v in attributed.items()]
    )
    return result, pd.DataFrame(matches)


def owner_segments(years: list[int]) -> pd.DataFrame:
    """Every (year, facility, owner name, share, facility co2e) row for the given years."""
    rows = []
    for year in years:
        joined = facility_totals(year).merge(facility_parents(year), on="facility_id", how="inner")
        for _, row in joined.iterrows():
            for owner_name, share in parse_owners(row["parent_company"]):
                rows.append({"year": year, "facility_id": row["facility_id"], "parent_company_raw": row["parent_company"],
                             "owner_segment": owner_name, "share": share, "facility_co2e_tonnes": row["co2e_tonnes"]})
    return pd.DataFrame(rows)


def match_owners(owners: pd.Series, universe: pd.DataFrame) -> pd.Series:
    """owner name -> ticker (first ticker of the CIK), None if no S&P 500 parent.

    1. social/scripts/_company_match.py: exact normalised parent name, former SEC names,
       or a subsidiary from the parent's 10-K Exhibit 21 ("WILLIAMS PARTNERS, LP" -> WMB).
    2. the original whole-word rule on the normalised S&P 500 name, now also comparing
       with spaces removed ("EXXONMOBIL CORP" = "Exxon Mobil"), GENERIC_NAMES exact only.
    Government/municipal owners are never matched.
    """
    from social.scripts._company_match import CompanyMatcher

    unique = pd.Series(sorted(set(owners.dropna())))
    unique = unique[~unique.map(lambda n: bool(GOVERNMENT_ENTITY_RE.search(normalise(n))))]
    first_ticker = universe.drop_duplicates("cik").assign(cik=lambda d: d["cik"].astype(str).str.zfill(10))
    first_ticker = dict(zip(first_ticker["cik"], first_ticker["ticker"]))
    by_matcher = CompanyMatcher().match(pd.Series([None] * len(unique), index=unique.index), unique)["cik"].map(first_ticker)

    name_index = {normalise(n): t for n, t in zip(universe["name"], universe["ticker"])}
    compact_index = {k.replace(" ", ""): t for k, t in name_index.items() if len(k.replace(" ", "")) >= 6}

    def by_rule(owner: str) -> str | None:
        norm = normalise(owner)
        compact = norm.replace(" ", "")
        for sp500_norm, ticker in name_index.items():
            if len(sp500_norm) < 6:
                if norm == sp500_norm:  # short names only as the WHOLE owner name: "AES CORP", "DOW INC"
                    return ticker
                continue
            if sp500_norm in GENERIC_NAMES:
                if norm == sp500_norm:
                    return ticker
            elif re.search(rf"\b{re.escape(sp500_norm)}\b", norm):
                return ticker
        return compact_index.get(compact)

    result = by_matcher.where(by_matcher.notna(), unique.map(by_rule))
    # A former SEC name that now belongs to a separate, spun-off company must not pull that
    # company's plants to the old parent: Howmet (HWM) was "Alcoa Inc." and "Arconic Inc.",
    # but GHGRP's "ALCOA CORP" (2016 spin-off) and "ARCONIC CORP" (2020 spin-off) are other
    # companies. Found by hand-checking the match log.
    # ("ARCONIC INC" in 2018-19 WAS Howmet and stays matched - only the spin-offs' own names are blocked)
    spun_off = {"ALCOA CORP", "ALCOA CORPORATION", "ARCONIC CORP", "ARCONIC CORPORATION"}
    blocked = unique.map(lambda n: " ".join(PUNCT_RE.sub(" ", n.upper()).split()) in spun_off)
    result = result.where(~blocked.values, None)
    return pd.Series(result.values, index=unique.values)


def build() -> pd.DataFrame:
    from environmental.scripts._revenue import load_revenue

    universe = load_universe()
    years = available_years()
    print(f"  EPA GHGRP years with published data: {years}")

    segments = owner_segments(years)
    owner_to_ticker = match_owners(segments["owner_segment"], universe)
    segments["ticker"] = segments["owner_segment"].map(owner_to_ticker)
    # "ARCONIC INC" was Howmet's name until the April 2020 split; from 2020 the name belongs
    # to the spun-off Arconic Corp (taken private 2023), so those facilities are not Howmet's
    late_arconic = (segments["ticker"] == "HWM") & (segments["year"] >= 2020) & segments["owner_segment"].str.upper().str.startswith("ARCONIC")
    segments.loc[late_arconic, "ticker"] = None
    matches = segments.dropna(subset=["ticker"]).copy()
    matches["attributed_co2e_tonnes"] = matches["facility_co2e_tonnes"] * matches["share"]
    MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
    matches.to_csv(MATCHES_PATH, index=False)
    print(f"  wrote {len(matches)} owner-name matches ({matches['ticker'].nunique()} companies) -> {MATCHES_PATH}")

    co2e = matches.groupby(["ticker", "year"])["attributed_co2e_tonnes"].sum()
    facilities = matches.groupby(["ticker", "year"])["facility_id"].nunique()
    revenue = load_revenue()
    cik_tickers: dict[str, list[str]] = {}
    for t, c in zip(universe["ticker"], universe["cik"]):
        cik_tickers.setdefault(str(c), []).append(t)

    rows, raw_rows = [], []
    for tickers in cik_tickers.values():
        # share classes: the facility owner matches the first class; every class gets the value
        key_ticker = next((t for t in tickers if any((t, y) in co2e.index for y in years)), tickers[0])
        for year in years:
            rev = revenue.get((tickers[0], year))
            if not rev:
                continue
            tonnes = float(co2e.get((key_ticker, year), 0.0))
            ratio = tonnes / (rev / 1e6)
            if tonnes > 0:
                note = (f"{tonnes:,.0f} tCO2e direct (Scope 1) from {int(facilities.get((key_ticker, year)))} GHGRP "
                        f"facilities, ownership-weighted, over revenue ${rev / 1e9:,.2f}bn")
            else:
                note = ("no US facility reporting to EPA GHGRP (>= 25,000 tCO2e/yr) found under the company's name, "
                        "former names or 10-K subsidiaries - direct US emissions below the reporting threshold, "
                        "not zero emissions")
            for ticker in tickers:
                rows.append({"ticker": ticker, "year": year, "value": round(ratio, 3), "source": SOURCE,
                             "source_url": "https://ghgdata.epa.gov/ghgp/main.do", "retrieved": today_utc(), "note": note})
            raw_rows.append({"ticker": tickers[0], "year": year, "co2e_tonnes": tonnes, "revenue_usd": rev, "raw_ratio": ratio})
    pd.DataFrame(raw_rows).to_csv(RAW_RATIO_PATH, index=False)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = build()
    write_indicator(CATEGORY, INDICATOR_ID, df)
    latest = df[df["year"] == df["year"].max()]
    print(f"  highest tCO2e per $M revenue in {int(df['year'].max())}:")
    print(latest.nlargest(10, "value")[["ticker", "value"]].to_string(index=False))
    print(f"  companies with a GHGRP facility that year: {(latest['value'] > 0).sum()} of {latest['ticker'].nunique()}")
