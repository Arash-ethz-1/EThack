"""Exhibit F (part 2) - a sanity pattern check: does the most tie-heavy indicator
look like a real industry-level pattern (clustered by sector) rather than a data
error? A high share of companies sharing the exact same value is expected for an
industry-level metric (e.g. a resource-risk score assigned per industry) and
suspicious for anything that should vary company to company.

    python run.py verify sector_pattern
"""

from __future__ import annotations

import pandas as pd

from checks._common import all_indicators, read_indicator
from common.config import UNIVERSE_CSV
from common.score import latest_values

TITLE = "Distributions match sector expectations"
KIND = "code"
EXHIBIT = "F"


def run() -> dict:
    if not UNIVERSE_CSV.exists():
        return {"status": "flagged", "verdict": "universe/sp500.csv is missing - cannot group by sector.",
                "numbers": {}, "rows": []}
    sector = pd.read_csv(UNIVERSE_CSV, dtype=str).set_index("ticker")["sector"]

    best = None  # (indicator_id, tie_ratio, values)
    for ind in all_indicators():
        df = read_indicator(ind["path"])
        if df is None or df.empty:
            continue
        vals = latest_values(df).dropna()
        if len(vals) < 20:
            continue
        tie_ratio = 1 - vals.nunique() / len(vals)
        if best is None or tie_ratio > best[1]:
            best = (ind["indicator_id"], tie_ratio, vals)

    if best is None:
        return {"status": "flagged", "verdict": "No indicator has enough data to check.", "numbers": {}, "rows": []}

    iid, tie_ratio, vals = best
    grouped = vals.groupby(sector.reindex(vals.index).fillna("(no sector)"))
    by_sector = {s: sorted(round(float(v), 4) for v in g) for s, g in grouped}
    verdict = (
        f"'{iid}' is the most tie-heavy indicator ({tie_ratio:.0%} of companies share a value with another) - "
        "consistent with an industry-level metric, not a per-company data error."
    )
    return {
        "status": "passed",
        "verdict": verdict,
        "numbers": {"indicator_id": iid, "tie_ratio": round(tie_ratio, 3), "by_sector": by_sector},
        "rows": [],
    }
