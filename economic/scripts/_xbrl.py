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


def annual_usd_facts(facts: dict, tags: list[str]) -> pd.DataFrame:
    """One row per fiscal year, merged across all given tags (in priority order).

    Companies switch XBRL tags over time (e.g. most switched revenue tags around
    2018-2019 for ASC 606) - a single company's history is often split across two
    tags, not fully covered by either alone. For a year reported under more than one
    tag, the earliest-listed tag in `tags` wins.

    Keeps only 10-K filings covering a full ~year (340-380 days), and when a fiscal
    year was restated / re-filed multiple times, keeps the most recently filed value.
    Returns columns: year, value, end, accn. Empty frame if none of the tags exist.
    """
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    frames = []
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
        df = df.sort_values("filed").drop_duplicates("fy", keep="last")
        df = df[["fy", "val", "end", "accn"]].rename(columns={"fy": "year", "val": "value"})
        df["tag_priority"] = priority
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["year", "value", "end", "accn"])

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["year", "tag_priority"]).drop_duplicates("year", keep="first")
    return combined[["year", "value", "end", "accn"]].sort_values("year").reset_index(drop=True)
