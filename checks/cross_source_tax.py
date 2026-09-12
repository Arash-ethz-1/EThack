"""Exhibit C (part 1) - recomputed independently, same result.

Compares our effective tax rate (income tax expense / pretax income, computed in
economic/scripts/tax_rate_gap.py) against the rate the company itself reports
under the XBRL tag `EffectiveIncomeTaxRateContinuingOperations` - a second,
independent route to (approximately) the same number. Companies that don't tag
that concept are skipped, not guessed.

    python run.py verify cross_source_tax
"""

from __future__ import annotations

import re

import pandas as pd

from common.config import indicator_path
from common.io import load_universe
from economic.scripts._xbrl import fetch_companyfacts

TITLE = "Recomputed independently, same result (tax rate)"
KIND = "code"
EXHIBIT = "C"
NOTE_RATE = re.compile(r"effective_rate=([-\d.]+)")
WITHIN = 0.01  # 1 percentage point


def xbrl_effective_rate(facts: dict, year: int) -> float | None:
    """The company's own `EffectiveIncomeTaxRateContinuingOperations` for one fiscal year,
    from a full-year (340-380 day) 10-K entry - the "pure" unit, not USD."""
    node = facts.get("facts", {}).get("us-gaap", {}).get("EffectiveIncomeTaxRateContinuingOperations")
    if not node:
        return None
    entries = node.get("units", {}).get("pure", [])
    if not entries:
        return None
    df = pd.DataFrame(entries)
    if df.empty or "form" not in df.columns:
        return None
    df = df[(df["form"] == "10-K") & (df["fy"] == year)]
    if "start" in df.columns and "end" in df.columns:
        days = (pd.to_datetime(df["end"]) - pd.to_datetime(df["start"])).dt.days
        df = df[(days >= 340) & (days <= 380)]
    if df.empty:
        return None
    return float(df.sort_values("filed").iloc[-1]["val"])


def run() -> dict:
    path = indicator_path("economic", "tax_rate_gap")
    df = None if not path.exists() else pd.read_csv(path)
    if df is None or df.empty:
        return {"status": "flagged", "verdict": "economic/indicators/tax_rate_gap.csv is missing or empty.",
                "numbers": {}, "rows": []}

    cik_of = load_universe().set_index("ticker")["cik"]
    latest = df.sort_values("year").groupby("ticker").tail(1)

    ours, theirs, tickers = [], [], []
    for _, r in latest.iterrows():
        m = NOTE_RATE.search(str(r["note"]))
        if not m or r["ticker"] not in cik_of.index:
            continue
        facts = fetch_companyfacts(cik_of[r["ticker"]], r["ticker"])
        if facts is None:
            continue
        xbrl_rate = xbrl_effective_rate(facts, int(r["year"]))
        if xbrl_rate is None:
            continue
        ours.append(float(m.group(1)))
        theirs.append(xbrl_rate)
        tickers.append(r["ticker"])

    if not ours:
        return {"status": "flagged", "verdict": "No companies tag EffectiveIncomeTaxRateContinuingOperations "
                "for a year we also have - nothing to cross-check yet.", "numbers": {}, "rows": []}

    within = sum(1 for o, t in zip(ours, theirs) if abs(o - t) <= WITHIN)
    share = within / len(ours)
    status = "passed" if share >= 0.7 else "flagged"
    verdict = f"{within} of {len(ours)} companies land within {WITHIN * 100:.0f} percentage point of the rate the company itself reports in XBRL."
    return {
        "status": status,
        "verdict": verdict,
        "numbers": {"tickers": tickers, "ours": ours, "theirs": theirs, "within": within, "checked": len(ours)},
        "rows": [],
    }
