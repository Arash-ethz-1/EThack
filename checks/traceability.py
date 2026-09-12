"""Exhibit A - every value points to a document.

Counts rows with a non-empty source_url across every indicator file that exists
(any status). Flags an indicator where a single source_url is shared by more than
5 companies - a generic API/search endpoint, not a document a human can open for
that one company (e.g. a shared search-results URL).

    python run.py verify traceability
"""

from __future__ import annotations

from checks._common import all_indicators, read_indicator

TITLE = "Every value points to a document"
KIND = "code"
EXHIBIT = "A"


def run() -> dict:
    total_rows, with_source = 0, 0
    per_indicator, flagged = [], []

    for ind in all_indicators():
        df = read_indicator(ind["path"])
        if df is None or df.empty:
            continue
        has_src = df["source_url"].astype(str).str.strip() != ""
        n = len(df)
        total_rows += n
        with_source += int(has_src.sum())
        per_indicator.append(
            {
                "indicator_id": ind["indicator_id"],
                "category": ind["category"],
                "companies": int(df["ticker"].nunique()),
                "rows": n,
                "with_source": int(has_src.sum()),
            }
        )
        n_companies = df["ticker"].nunique()
        if df["source_url"].nunique() == 1 and n_companies > 5:
            flagged.append(
                {
                    "ticker": "",
                    "year": None,
                    "indicator_id": ind["indicator_id"],
                    "value": None,
                    "detail": f"all {n_companies} companies share one source_url - a generic endpoint, "
                    "not a per-company document",
                    "url": df["source_url"].iloc[0],
                }
            )

    status = "flagged" if flagged else "passed"
    verdict = f"{with_source:,} of {total_rows:,} values carry a link to their public source."
    return {"status": status, "verdict": verdict, "numbers": {"per_indicator": per_indicator}, "rows": flagged}
