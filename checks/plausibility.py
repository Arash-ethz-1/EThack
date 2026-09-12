"""Exhibit D (code half) - outliers are real, not errors.

Flags, across every indicator file: years in the future, year-over-year changes
beyond 3x the interquartile range of that indicator's own changes, and latest-year
levels beyond 3x the interquartile range of that indicator's own levels. Both
fences are relative to the indicator itself, not a universal ratio - a flat "5x
jump" rule looked right for something like revenue but flagged 1,067 ordinary
year-to-year swings in tax_rate_gap alone (a small number that swings around and
across zero, where "5x" stops meaning anything). Flagging is not deleting - a
human (or, once built, agent_outlier_explain) reads each one.

    python run.py verify plausibility
"""

from __future__ import annotations

import datetime as dt

import pandas as pd

from checks._common import all_indicators, read_indicator

TITLE = "Outliers are real, not errors"
KIND = "code"
EXHIBIT = "D"


def run() -> dict:
    this_year = dt.datetime.now(dt.timezone.utc).year
    rows = []

    for ind in all_indicators():
        df = read_indicator(ind["path"])
        if df is None or df.empty:
            continue
        iid = ind["indicator_id"]

        future = df[df["year"] > this_year + 1]
        for _, r in future.iterrows():
            rows.append(
                {
                    "ticker": r["ticker"],
                    "year": int(r["year"]),
                    "indicator_id": iid,
                    "value": float(r["value"]),
                    "detail": f"year {int(r['year'])} is in the future",
                    "url": r["source_url"],
                }
            )

        transitions = []  # (ticker, y0, v0, y1, v1, url1, delta)
        for ticker, g in df.sort_values("year").groupby("ticker"):
            g = g[["year", "value", "source_url"]].values
            for i in range(1, len(g)):
                y0, v0, _ = g[i - 1]
                y1, v1, url1 = g[i]
                if y1 - y0 == 1:
                    transitions.append((ticker, y0, v0, y1, v1, url1, v1 - v0))
        if len(transitions) >= 20:
            deltas = pd.Series([t[6] for t in transitions])
            q1, q3 = deltas.quantile(0.25), deltas.quantile(0.75)
            iqr = q3 - q1
            lo, hi = (q1 - 3 * iqr, q3 + 3 * iqr) if iqr > 0 else (float("-inf"), float("inf"))
            # iqr == 0 means over half the changes are identical (typically 0, e.g. a
            # ratio near-zero for most companies most years) - no meaningful "normal
            # range" to define, so nothing gets flagged rather than flagging almost
            # every nonzero change against a fence that collapsed to a point
            for ticker, y0, v0, y1, v1, url1, delta in transitions:
                if delta < lo or delta > hi:
                    rows.append(
                        {
                            "ticker": ticker,
                            "year": int(y1),
                            "indicator_id": iid,
                            "value": float(v1),
                            "detail": f"year-over-year change {delta:+.4g} is outside this indicator's typical "
                            f"range [{lo:.4g}, {hi:.4g}] - from {v0:.4g} ({int(y0)}) to {v1:.4g} ({int(y1)})",
                            "url": url1,
                        }
                    )

        latest_year = df["year"].max()
        latest = df[df["year"] == latest_year]
        if len(latest) >= 20:
            q1, q3 = latest["value"].quantile(0.25), latest["value"].quantile(0.75)
            iqr = q3 - q1
            lo, hi = (q1 - 3 * iqr, q3 + 3 * iqr) if iqr > 0 else (float("-inf"), float("inf"))
            for _, r in latest[(latest["value"] < lo) | (latest["value"] > hi)].iterrows():
                rows.append(
                    {
                        "ticker": r["ticker"],
                        "year": int(r["year"]),
                        "indicator_id": iid,
                        "value": float(r["value"]),
                        "detail": f"beyond the 3x IQR fence [{lo:.4g}, {hi:.4g}] for {int(latest_year)}",
                        "url": r["source_url"],
                    }
                )

    status = "flagged" if rows else "passed"
    verdict = f"{len(rows)} value(s) flagged as implausible or statistical outliers. Each gets read, not deleted."
    return {"status": status, "verdict": verdict, "numbers": {"count": len(rows)}, "rows": rows}
