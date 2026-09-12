"""Shared helper: the S&P 500 company list with GICS sub-industry.

Why this exists: universe/sp500.csv (Arash) has ticker, name, sector, cik but no
GICS *sub-industry*, and resource exposure differs enormously inside one sector
(Semiconductors vs Application Software are both Information Technology). This
helper adds the sub-industry column, and stands in for universe/sp500.csv while
that file does not exist yet.

Not an indicator - the leading underscore keeps `python run.py build` from running it.
"""

from __future__ import annotations

import pandas as pd

from common.io import cached_download, load_universe

CATEGORY = "environmental"
CONSTITUENTS_FILE = "sp500_constituents.csv"

# Same list Wikipedia's "List of S&P 500 companies" table is built from, as a plain
# CSV so we need no HTML parser. Columns: Symbol, Security, GICS Sector,
# GICS Sub-Industry, Headquarters Location, Date added, CIK, Founded.
CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)


def load_constituents(refresh: bool = False) -> pd.DataFrame:
    """S&P 500 constituents with GICS sector and sub-industry.

    Index membership changes several times a year, so this follows the same
    quarterly refresh rule as the risk sources.
    """
    from _resource_risk import is_stale

    path = cached_download(
        CONSTITUENTS_URL, CATEGORY, CONSTITUENTS_FILE, refresh=refresh or is_stale(CONSTITUENTS_FILE)
    )
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.rename(
        columns={
            "Symbol": "ticker",
            "Security": "name",
            "GICS Sector": "sector",
            "GICS Sub-Industry": "sub_industry",
            "CIK": "cik",
        }
    )
    df["ticker"] = df["ticker"].str.strip().str.upper().str.replace("-", ".", regex=False)
    df["cik"] = df["cik"].str.strip().str.zfill(10)
    return df[["ticker", "name", "sector", "sub_industry", "cik"]]


def load_universe_with_sub_industry(refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """Return (universe with a sub_industry column, description of where it came from).

    Uses universe/sp500.csv as the ticker list when Arash has built it, so our rows
    always match everyone else's. Falls back to the constituents file until then.
    """
    constituents = load_constituents(refresh=refresh)
    try:
        official = load_universe()
    except FileNotFoundError:
        return constituents, "sp500_constituents.csv (universe/sp500.csv does not exist yet)"

    official = official.copy()
    official["ticker"] = official["ticker"].str.strip().str.upper()
    merged = official.merge(
        constituents[["ticker", "sub_industry"]], on="ticker", how="left", validate="one_to_one"
    )
    missing = int(merged["sub_industry"].eq("").sum() + merged["sub_industry"].isna().sum())
    return merged, f"universe/sp500.csv joined to sp500_constituents.csv ({missing} without sub-industry)"
