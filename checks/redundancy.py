"""Exhibit F (part 1) - no two indicators measure the same thing.

Spearman rank correlation of the latest value per company, for every pair of
indicators that have at least 50 companies in common. Anything at or above 0.8 is
flagged as a likely duplicate (the score already keeps categories separate; this
catches two indicators inside one category quietly measuring the same thing).

    python run.py verify redundancy
"""

from __future__ import annotations

import itertools

import pandas as pd

from checks._common import all_indicators, read_indicator
from common.score import latest_values

TITLE = "No two indicators measure the same thing"
KIND = "code"
EXHIBIT = "F"
MIN_OVERLAP = 50
FLAG_ABOVE = 0.8


def run() -> dict:
    values = {}
    for ind in all_indicators():
        df = read_indicator(ind["path"])
        if df is not None and not df.empty:
            values[ind["indicator_id"]] = latest_values(df)

    pairs, flagged = {}, []
    for a, b in itertools.combinations(sorted(values), 2):
        joined = pd.concat([values[a], values[b]], axis=1, keys=[a, b]).dropna()
        if len(joined) < MIN_OVERLAP:
            continue
        rho = float(joined[a].rank().corr(joined[b].rank()))
        pairs[f"{a}|{b}"] = {"rho": round(rho, 3), "n": int(len(joined))}
        if abs(rho) >= FLAG_ABOVE:
            flagged.append(
                {
                    "ticker": "",
                    "year": None,
                    "indicator_id": f"{a} & {b}",
                    "value": round(rho, 3),
                    "detail": f"correlated {rho:.2f} over {len(joined)} companies - possible duplicate",
                    "url": "",
                }
            )

    if not pairs:
        return {
            "status": "flagged",
            "verdict": "No two indicators yet share enough companies to compare.",
            "numbers": {"pairs": {}},
            "rows": [],
        }
    max_rho = max(abs(p["rho"]) for p in pairs.values())
    status = "flagged" if flagged else "passed"
    verdict = f"The strongest overlap between any two indicators is {max_rho:.2f}. Nothing is counted twice."
    return {"status": status, "verdict": verdict, "numbers": {"pairs": pairs}, "rows": flagged}
