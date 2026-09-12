"""federal_contract_exposure - share of revenue that depends on federal contracts.

What it measures: for each company, direct federal *procurement* contract
obligations (USASpending award types A-D, i.e. actual contracts, not grants or
loans) as a share of that year's revenue. Higher means more of the company's
revenue is structurally exposed to a federal budget, appropriations or policy
shift on its prime contracts.

Category: economic (moved from environmental on 2026-09-13 - it measures how
dependent a company's revenue is on one customer, the US federal budget, not an
environmental impact).

Method, in full:
  1. Quarterly revenue from SEC XBRL (`data.sec.gov` companyconcept), bucketed by
     the real reporting period dates rather than SEC's own fy/fp labels, which
     mix comparative periods (see `_federal_contract_fetch.py` for why).
  2. Quarterly federal contract obligations from USASpending.gov, searched by each
     company's SEC legal name (informal display names like "IBM" silently return
     $0 - see `_federal_contract_fetch.py`), converted from USASpending's federal
     fiscal months to real calendar quarters.
  3. Annual value = (sum of the year's quarterly obligations) / (sum of the year's
     quarterly revenue), clipped to [0,1]. A same-year sum is used instead of a
     single quarter's ratio because obligations are booked when a contract is
     awarded while revenue is recognised as work is delivered - a single quarter
     can show a ratio far over 1.0 around a big award, which a same-year sum
     mostly smooths out (clipping catches what is left).
  4. A year needs at least 2 quarters of usable revenue data to get a row -
     partial-year data is not extrapolated into a full-year number.

What this does NOT capture (see git history "[infra] explore federal contract
concentration risk score" for the fuller writeup): subcontractor exposure (a
components supplier to Lockheed is invisible here unless it holds prime contracts
itself), or a subsidiary that contracts under a different legal name than its
parent (e.g. a cloud division). Treat this as a lower bound on federal exposure.

Sources:
  SEC EDGAR XBRL companyconcept (quarterly revenue)
  https://data.sec.gov/api/xbrl/companyconcept/
  USASpending.gov spending_over_time (federal procurement obligations)
  https://api.usaspending.gov/api/v2/search/spending_over_time/

Owner:  Jean
Run:    python run.py build economic federal_contract_exposure
Refresh cadence: quarterly - new 10-Qs and contract obligations post continuously.

Output: economic/indicators/federal_contract_exposure.csv (docs/DATA_FORMAT.md)
Also writes the full quarterly panel (all companies, all quarters, both raw series)
to economic/raw/federal_contract_quarterly_panel.csv for anyone who wants
quarter-level detail - the official indicator can only carry one row per company
per year (docs/DATA_FORMAT.md).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from common.config import raw_dir
from common.io import load_universe, today_utc, write_indicator

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _federal_contract_fetch import (  # noqa: E402
    build_company_panel,
    clean_recipient_name,
    get_sec_legal_names,
    verify_recipient_name,
)

CATEGORY = "economic"
INDICATOR_ID = "federal_contract_exposure"
SOURCE = "SEC XBRL quarterly revenue + USASpending.gov federal contract obligations"

CACHE_DIR = raw_dir(CATEGORY) / "federal_contract"
PANEL_PATH = raw_dir(CATEGORY) / "federal_contract_quarterly_panel.csv"
NAME_CHECK_PATH = raw_dir(CATEGORY) / "federal_contract_name_verification.csv"

START_DATE = "2018-01-01"
YEARS = list(range(2018, 2026))
MIN_QUARTERS = 2  # a year needs at least this many quarters of revenue to get a row

# A name-search collision (see verify_recipient_name) shows up as an implausibly
# large ratio - PPL Corporation and UDR Inc, both real cases found in this data,
# came back at 6.2x and 3.8x revenue. A company's tiny or zero ratio is not at risk
# of being a collision artifact even when its name search cannot be independently
# verified (most unverified names are exactly $0 - a company that has simply never
# held a federal contract, which is the correct answer, not a data gap). Only
# require verification for the ratios large enough that a collision is plausible.
MAX_UNVERIFIED_RATIO = 0.3

# Even a "verified" very short name (<=3 letters, e.g. "F5") can have its dollar
# total silently blended with other recipients that merely contain the same letters
# (F5 Networks came back at 115-123% of its own revenue two years running - it is
# genuinely registered as "F5" so verify_recipient_name passes it, but that total is
# almost certainly summing in other "F5"-containing recipients too). A ratio over
# 100% is an extraordinary claim; for a name this short and generic we do not trust
# it even when verified. Contrast Moderna's real 2020 Operation Warp Speed spike
# (>500% of that year's tiny revenue) - a long, distinctive search name, kept as-is.
SHORT_NAME_LEN = 3


def fetch_all_panels(refresh: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    constituents = load_universe()  # ticker, name, sector, cik
    legal_names = get_sec_legal_names(CACHE_DIR)
    end_date = today_utc()

    frames = []
    checks = []
    failed = []
    for i, row in constituents.iterrows():
        ticker, cik = row["ticker"], int(row["cik"])
        raw_name = legal_names.get(ticker, row["name"])
        name = clean_recipient_name(raw_name)
        verified, matched_as = verify_recipient_name(name, CACHE_DIR)
        checks.append({"ticker": ticker, "search_name": name, "verified": verified, "matched_as": matched_as})
        try:
            panel = build_company_panel(ticker, name, cik, START_DATE, end_date, CACHE_DIR)
        except Exception as e:
            failed.append((ticker, str(e)))
            continue
        if not panel.empty:
            frames.append(panel)
        if (i + 1) % 50 == 0:
            print(f"  fetched {i + 1}/{len(constituents)} companies")

    if failed:
        print(f"  {len(failed)} companies failed: {failed[:10]}")
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    PANEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_PATH, index=False)
    print(f"  wrote quarterly panel: {len(panel)} rows, {panel['ticker'].nunique()} tickers -> {PANEL_PATH}")

    checks_df = pd.DataFrame(checks)
    checks_df.to_csv(NAME_CHECK_PATH, index=False)
    unverified = checks_df[~checks_df["verified"]]
    print(f"  name verification: {len(checks_df) - len(unverified)}/{len(checks_df)} confirmed via USASpending autocomplete")
    if len(unverified):
        print(f"  {len(unverified)} unverified (obligations excluded, not trusted): {list(unverified['ticker'])}")
    return panel, checks_df


def annualise(panel: pd.DataFrame, checks_df: pd.DataFrame) -> pd.DataFrame:
    panel = panel[panel["year"].isin(YEARS) & panel["revenue_usd"].notna()]

    verified_tickers = set(checks_df.loc[checks_df["verified"].astype(bool), "ticker"])
    name_len = checks_df.set_index("ticker")["search_name"].str.replace(
        r"[^A-Za-z0-9]", "", regex=True
    ).str.len()

    agg = panel.groupby(["ticker", "year"]).agg(
        revenue=("revenue_usd", "sum"),
        obligations=("contract_obligations_usd", "sum"),
        n_quarters=("quarter", "nunique"),
    ).reset_index()
    agg = agg[(agg["n_quarters"] >= MIN_QUARTERS) & (agg["revenue"] > 0)]

    raw_ratio = agg["obligations"] / agg["revenue"]

    # Only rows where a name-search collision could plausibly explain the number
    # need the independent autocomplete confirmation; a small or zero ratio is not
    # at risk of being a collision artifact even when its name search cannot be
    # independently verified (most unverified names are exactly $0 - a company that
    # has simply never held a federal contract, which is correct, not a data gap).
    unverified_and_implausible = (raw_ratio > MAX_UNVERIFIED_RATIO) & ~agg["ticker"].isin(verified_tickers)

    # A ratio over 100% needs a name distinctive enough to trust even when verified
    # (see SHORT_NAME_LEN above) - a genuine autocomplete match for a 2-3 letter name
    # does not rule out the dollar total also including other same-letter recipients.
    ticker_name_len = agg["ticker"].map(name_len)
    over_100pct_and_short_name = (raw_ratio > 1.0) & (ticker_name_len <= SHORT_NAME_LEN)

    drop = unverified_and_implausible | over_100pct_and_short_name
    dropped = sorted(set(agg.loc[drop, "ticker"]))
    if dropped:
        print(f"  dropping {len(dropped)} companies: implausible ratio with no reliable name match: {dropped}")
    agg = agg[~drop]
    raw_ratio = raw_ratio[~drop]

    agg["clipped"] = raw_ratio > 1.0
    agg["value"] = raw_ratio.clip(0, 1).round(4)

    agg["source"] = SOURCE
    agg["source_url"] = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
    agg["retrieved"] = today_utc()
    agg["note"] = (
        agg["n_quarters"].astype(str)
        + "/4 quarters, obligations $"
        + agg["obligations"].round(0).astype("int64").astype(str)
        + " / revenue $"
        + agg["revenue"].round(0).astype("int64").astype(str)
        + agg["clipped"].map({True: " (raw ratio over 1.0, clipped)", False: ""})
    )
    return agg[["ticker", "year", "value", "source", "source_url", "retrieved", "note"]]


def verify_all_names(refresh: bool = False) -> pd.DataFrame:
    """Name-verification pass only, reusable without re-fetching quarterly data."""
    constituents = load_universe()  # ticker, name, sector, cik
    legal_names = get_sec_legal_names(CACHE_DIR)
    checks = []
    for _, row in constituents.iterrows():
        name = clean_recipient_name(legal_names.get(row["ticker"], row["name"]))
        verified, matched_as = verify_recipient_name(name, CACHE_DIR)
        checks.append({"ticker": row["ticker"], "search_name": name, "verified": verified, "matched_as": matched_as})
    checks_df = pd.DataFrame(checks)
    checks_df.to_csv(NAME_CHECK_PATH, index=False)
    return checks_df


def build() -> pd.DataFrame:
    if PANEL_PATH.exists():
        panel = pd.read_csv(PANEL_PATH)
        print(f"  reusing cached quarterly panel: {len(panel)} rows (delete {PANEL_PATH.name} to refetch)")
    else:
        panel, _ = fetch_all_panels()

    if NAME_CHECK_PATH.exists():
        checks_df = pd.read_csv(NAME_CHECK_PATH)
    else:
        checks_df = verify_all_names()

    n_verified = int(checks_df["verified"].astype(bool).sum())
    print(f"  name verification: {n_verified}/{len(checks_df)} confirmed via USASpending autocomplete")

    return annualise(panel, checks_df)


if __name__ == "__main__":
    df = build()
    write_indicator(CATEGORY, INDICATOR_ID, df)

    latest = df[df["year"] == df["year"].max()]
    print(f"\n  most federal-contract-exposed companies in {int(df['year'].max())}:")
    print(latest.nlargest(15, "value")[["ticker", "value", "note"]].to_string(index=False))
    print(f"\n  coverage: {df['ticker'].nunique()} / 503 companies have >=1 year scored")
