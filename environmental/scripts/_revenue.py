"""Annual revenue per (ticker, fiscal year) for environmental/ indicators - a helper, not an indicator.

1. social/raw/financials.csv + universe/financials.csv via social's load_revenue (SEC XBRL frames)
2. fallback for tickers missing there: SEC XBRL companyfacts through economic/scripts/_xbrl.py
   (same cache, fiscal year = year the period ends), with economic's CIK overrides
   (XOM: sp500.csv lists the new holding company CIK 0002115436, whose filings do not yet
   carry the revenue history of Exxon Mobil Corporation, CIK 0000034088).

Leading underscore = `python run.py build environmental` skips this file.
"""

from __future__ import annotations

from common.io import load_universe
from economic.scripts._headcount import CIK_OVERRIDES
from economic.scripts._xbrl import annual_usd_facts, fetch_companyfacts
from economic.scripts.revenue_volatility import REVENUE_TAGS
from social.scripts.labor_litigation_intensity import load_revenue as load_frames_revenue


def load_revenue(first_year: int = 2015) -> dict[tuple[str, int], float]:
    revenue = load_frames_revenue()
    have = {t for t, _ in revenue}
    added = []
    universe = load_universe()
    for ticker, cik in zip(universe["ticker"], universe["cik"]):
        if ticker in have:
            continue
        facts = fetch_companyfacts(CIK_OVERRIDES.get(ticker, cik), ticker)
        if not facts:
            continue
        rows = annual_usd_facts(facts, REVENUE_TAGS)
        for _, r in rows[rows["year"] >= first_year].iterrows():
            if r["value"] > 0:
                revenue[(ticker, int(r["year"]))] = float(r["value"])
        if not rows.empty:
            added.append(ticker)
    print(f"revenue fallback from SEC companyfacts for {len(added)} tickers: {added}")
    return revenue
