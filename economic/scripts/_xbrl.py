"""Shared SEC XBRL company-facts helpers for economic/ indicator scripts.

Not an indicator itself - imported by tax_rate_gap.py, revenue_volatility.py, etc.
Every call goes through common.io.cached_json, so a company is only ever downloaded once.
"""

from __future__ import annotations

import pandas as pd

from common.io import cached_json

COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


def fetch_companyfacts(cik: str, ticker: str) -> dict | None:
    """Download (once, cached to economic/raw/) a company's full XBRL facts.

    Returns None if SEC has nothing under this CIK (e.g. recent IPO, no 10-K yet).
    """
    cik10 = str(cik).zfill(10)
    try:
        return cached_json(
            COMPANYFACTS_URL.format(cik=cik10), "economic", f"companyfacts_{cik10}.json"
        )
    except Exception as e:  # 404 / not found - not fatal, just no data for this company
        print(f"  skip {ticker} ({cik10}): {e}")
        return None


def fiscal_year_from_end(end: pd.Series) -> pd.Series:
    """Fiscal year = calendar year the period ENDS in; a 52/53-week year ending Jan 1-7 counts as the year before."""
    end = pd.to_datetime(end)
    early_january = (end.dt.month == 1) & (end.dt.day <= 7)
    return end.dt.year - early_january.astype(int)


def annual_usd_facts(facts: dict, tags: list[str]) -> pd.DataFrame:
    """One row per fiscal year, merged across all given tags (in priority order).

    Companies switch XBRL tags over time (e.g. most switched revenue tags around
    2018-2019 for ASC 606) - a single company's history is often split across two
    tags, not fully covered by either alone. For a year reported under more than one
    tag, the earliest-listed tag in `tags` wins.

    Keeps only 10-K filings covering a full ~year (340-380 days), and when a fiscal
    year was restated / re-filed multiple times, keeps the most recently filed value.
    Returns columns: year, value, end, accn. Empty frame if none of the tags exist.

    `year` is the fiscal year the value covers = the calendar year in which that
    fiscal year ENDS (a 52/53-week year ending Jan 1-7 counts as the year before, e.g. a
    year ending 2022-01-01 is 2021). Derived from the period end date only - NOT from
    SEC's `fy` field. `fy` is the fiscal-year focus of the *filing*: a 10-K also carries
    2 prior years as comparatives, all tagged with the filing's `fy`, and filers tag it
    inconsistently (Seagate's FY2025 10-K, filed 2025-08-01, says fy=2027; Kroger tagged
    three consecutive fiscal years 2024, 2025, 2025). Deduplicating on `fy` kept an
    arbitrary period per filing and produced impossible future years (2027). With the
    end-date rule Microsoft's year ending 2026-06-30 is 2026 and Walmart's year ending
    2026-01-31 is 2026 (both match their own label); retailers that name the year after
    its start (Home Depot's "fiscal 2025" ending 2026-02-01) appear as 2026. The same
    rule for every company and every tag, so tax and pretax income of one period
    always get the same year.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    tag_frames = []
    for priority, tag in enumerate(tags):
        node = us_gaap.get(tag)
        if not node:
            continue
        entries = node.get("units", {}).get("USD", [])
        if not entries:
            continue
        df = pd.DataFrame(entries)
        if df.empty or "form" not in df.columns or "start" not in df.columns:
            continue
        df = df[df["form"] == "10-K"]
        days = (pd.to_datetime(df["end"]) - pd.to_datetime(df["start"])).dt.days
        df = df[(days >= 340) & (days <= 380)]
        if df.empty:
            continue
        tag_frames.append(df.assign(tag_priority=priority))

    if not tag_frames:
        return pd.DataFrame(columns=["year", "value", "end", "accn"])

    frames = []
    for df in tag_frames:
        df = df.assign(year=fiscal_year_from_end(df["end"]))
        # same year: the latest-ending period wins (fiscal-year-end change), then the
        # most recent filing (restatement)
        df = df.sort_values(["end", "filed"], kind="stable").drop_duplicates("year", keep="last")
        frames.append(df[["year", "val", "end", "accn", "tag_priority"]].rename(columns={"val": "value"}))

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["year", "tag_priority"]).drop_duplicates("year", keep="first")
    return combined[["year", "value", "end", "accn"]].sort_values("year").reset_index(drop=True)
