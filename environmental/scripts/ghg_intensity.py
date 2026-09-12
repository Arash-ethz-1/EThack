"""ghg_intensity - carbon intensity of S&P 500 companies with large US industrial facilities.

What it measures: for each company that owns at least one facility big enough to be
required to report to EPA's Greenhouse Gas Reporting Program (GHGRP, 40 CFR Part 98 -
power plants, refineries, cement/steel/chemical plants, etc.), its facilities' Scope 1
CO2e emissions - split across owners by the ownership share GHGRP itself records -
divided by that year's revenue (SEC XBRL). Higher = more direct emissions per dollar
of revenue that year. A missing company means "no GHGRP facility found under its
name", not "zero emissions" or "clean" - most services/finance/tech/retail companies
have no such facility and are correctly absent, not scored as good.

Method, in full:
  1. EPA Envirofacts GHGRP:
     - RLPS_GHG_EMITTER_GAS: facility x year x gas -> co2e_emission (tonnes),
       summed per facility_id + year to a facility-year total.
     - PUB_DIM_FACILITY: facility x year -> free-text `parent_company`, e.g.
       "Exxon Mobil Corp (100%)" or several co-owners with a % each - GHGRP requires
       filers to report their ownership share of a facility, so this is EPA's own
       reported split, not an assumption this script adds.
  2. Each parent_company string is split on ";" into (name, ownership share) pairs
     (share = 1.0 when no "(NN%)" is present). A facility's total emissions are
     multiplied by each owner's share before being attributed to that owner.
  3. Each owner name is matched to `universe/sp500.csv` by normalising both sides
     (uppercase, drop Inc/Corp/Corporation/Co/Company/The/LLC/LLP/LP/PLC/Ltd/
     Holdings/Group/plc, punctuation) and requiring the full normalised S&P 500 name
     (>= 6 characters, to avoid short-name false positives) to appear in the
     normalised owner text as a whole word (word-boundary, not a raw substring - a
     3-letter ticker cannot match inside an unrelated longer word). A name that
     normalises to a common English/geographic word alone (e.g. "Southern Co" ->
     "SOUTHERN", which also matches "Southern California Public Power Authority", or
     "Waste Management, Inc." -> "WASTE MANAGEMENT", which also matches dozens of
     unrelated county "Solid Waste Management" agencies) is required to match the
     owner text *exactly* instead - see GENERIC_NAMES. An owner segment naming a
     government/municipal body (county, city, authority, district, cooperative, ...)
     is skipped outright before matching - see GOVERNMENT_ENTITY_RE - since no
     S&P 500 company's own name contains those words. Both found by hand-checking
     the match log per AGENTS.md rule 6. Matched shares are summed per ticker + year.
     Every match is written to environmental/raw/ghg_intensity_matches.csv for a
     human to spot-check; this remains a heuristic name match, not a certified
     ownership record - re-check the log after every rebuild.
  4. Revenue per ticker + fiscal year from SEC XBRL companyconcept: first of
     Revenues / RevenueFromContractWithCustomerExcludingAssessedTax /
     RevenueFromContractWithCustomerIncludingAssessedTax / SalesRevenueNet that has
     a 10-K annual fact (duration 350-380 days) for that fiscal year.
  5. raw_ratio = attributed tCO2e / (revenue_usd / 1e6) = tCO2e per $M revenue.

Deviation from docs/DATA_FORMAT.md, done on Jean's explicit instruction: the `value`
column is NOT the raw ratio in its native unit. It is the raw ratio's percentile
rank *within this indicator's own matched companies, that year* (0 = lowest carbon
intensity among matched peers = best, 1 = highest = worst), so it already sits in
[0,1] instead of leaving 0-1 normalisation to common/score.py's percentile rank over
the full universe. Consequences, so a reader is not misled:
  - This is a rank among the ~handful of matched heavy emitters, not among all 503
    companies - it says nothing about how a matched company compares to one with no
    GHGRP facility at all.
  - Percentile ranks are correct, but plain, unlabelled floats: this file cannot be
    told apart from a "properly" 0-1 unit indicator like resource_supply_risk just
    by looking at `value`. See catalog `unit` and this docstring for the difference.
  - common/score.py will percentile-rank this already-percentile-ranked number
    again, compressing it further. Flagged to Arash - see commit message; not
    changed here because common/score.py is shared infrastructure Jean does not own.

Coverage: well under the 70% S&P 500 bar for `ready` (docs/AGENTS.md #4) - GHGRP only
reaches direct heavy industrial/power/energy emitters. Left as `in_progress`.

No 2024/2025 rows: GHGRP reporting-year-2024 data was not yet published by EPA as of
2026-09-12 (RLPS_GHG_EMITTER_GAS returns 0 rows for year 2024) - a missing year, not
a zero, and is not filled in or estimated (AGENTS.md rule 6).

No quarterly rows: also requested, not built. GHGRP - like every other public GHG
disclosure checked for this indicator - is an annual figure; no company reports
quarterly Scope 1/2 emissions, so quarterly rows would mean inventing numbers
(AGENTS.md rule 6, not overridden by the normalisation request above). Separately,
the shared indicator format has one row per ticker+year (common/config.py,
Arash's file, `environmental/` does not own it) with no quarter column - social
already has an open request for one (see git history). Both are blockers independent
of the 0-1 request; raise the need for a quarter column with Arash if still wanted.

Sources:
  EPA Envirofacts GHGRP API (facility emissions + reported ownership)
  https://data.epa.gov/efservice/RLPS_GHG_EMITTER_GAS
  https://data.epa.gov/efservice/PUB_DIM_FACILITY
  SEC EDGAR XBRL companyconcept (annual revenue)
  https://data.sec.gov/api/xbrl/companyconcept/

Owner:  Jean
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


def sec_annual_revenue(cik: str, year: int) -> float | None:
    tags = [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
    ]
    cik10 = str(cik).zfill(10)
    for tag in tags:
        try:
            data = cached_json(
                f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json",
                CATEGORY,
                f"sec_revenue_{cik10}_{tag}.json",
            )
        except requests.HTTPError:
            continue
        facts = data.get("units", {}).get("USD", [])
        for f in facts:
            if f.get("form") != "10-K" or f.get("fy") != year:
                continue
            try:
                start = pd.Timestamp(f["start"])
                end = pd.Timestamp(f["end"])
            except (KeyError, ValueError):
                continue
            if 350 <= (end - start).days <= 380:
                return float(f["val"])
    return None


def build() -> pd.DataFrame:
    universe = load_universe()
    name_index = {normalise(row["name"]): row["ticker"] for _, row in universe.iterrows()}
    cik_by_ticker = dict(zip(universe["ticker"], universe["cik"]))

    years = available_years()
    print(f"  EPA GHGRP years with published data: {years}")

    year_frames, match_frames = [], []
    for year in years:
        result, matches = match_year(year, name_index)
        if not result.empty:
            year_frames.append(result)
        if not matches.empty:
            match_frames.append(matches)
        print(f"  {year}: {len(result)} companies matched to a GHGRP facility")

    co2e = pd.concat(year_frames, ignore_index=True) if year_frames else pd.DataFrame(columns=["ticker", "year", "co2e_tonnes"])
    matches_log = pd.concat(match_frames, ignore_index=True) if match_frames else pd.DataFrame()
    if not matches_log.empty:
        MATCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
        matches_log.to_csv(MATCHES_PATH, index=False)
        print(f"  wrote {len(matches_log)} owner-name matches -> {MATCHES_PATH} (spot-check these)")

    rows = []
    for _, r in co2e.iterrows():
        cik = cik_by_ticker.get(r["ticker"])
        if cik is None:
            continue
        revenue = sec_annual_revenue(cik, int(r["year"]))
        if not revenue or revenue <= 0:
            continue
        rows.append(
            {
                "ticker": r["ticker"],
                "year": int(r["year"]),
                "co2e_tonnes": r["co2e_tonnes"],
                "revenue_usd": revenue,
                "raw_ratio": r["co2e_tonnes"] / (revenue / 1e6),
            }
        )
    raw = pd.DataFrame(rows)
    if raw.empty:
        raise RuntimeError("no ticker matched both a GHGRP facility and SEC revenue - nothing to write")

    raw_ratio_out = raw.copy()
    raw_ratio_out["source"] = SOURCE
    raw_ratio_out["source_url"] = "https://data.epa.gov/efservice/RLPS_GHG_EMITTER_GAS"
    raw_ratio_out["retrieved"] = today_utc()
    RAW_RATIO_PATH.parent.mkdir(parents=True, exist_ok=True)
    raw_ratio_out.to_csv(RAW_RATIO_PATH, index=False)
    print(f"  wrote raw tCO2e/$M-revenue ratios -> {RAW_RATIO_PATH}")

    raw["value"] = raw.groupby("year")["raw_ratio"].rank(pct=True).round(4)
    raw["source"] = SOURCE
    raw["source_url"] = "https://data.epa.gov/efservice/RLPS_GHG_EMITTER_GAS"
    raw["retrieved"] = today_utc()
    raw["note"] = (
        "percentile rank of "
        + raw["raw_ratio"].round(1).astype(str)
        + " tCO2e/$M revenue among "
        + raw.groupby("year")["ticker"].transform("count").astype(str)
        + " GHGRP-matched companies that year (see ghg_intensity_raw_ratio.csv)"
    )
    return raw[["ticker", "year", "value", "source", "source_url", "retrieved", "note"]]


if __name__ == "__main__":
    df = build()
    write_indicator(CATEGORY, INDICATOR_ID, df)
    latest = df[df["year"] == df["year"].max()]
    print(f"\n  highest carbon intensity (percentile) in {int(df['year'].max())}:")
    print(latest.nlargest(10, "value")[["ticker", "value"]].to_string(index=False))
    print(f"\n  coverage: {df['ticker'].nunique()} / 503 companies have >=1 year scored")
