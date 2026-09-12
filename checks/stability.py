"""Exhibit E - company traits persist over time.

Spearman rank correlation of each indicator's value with its own previous year,
over companies present in both years (at least 100). Random noise would sit near
0; a real, persistent company trait should sit well above it. Uses
`a.rank().corr(b.rank())` instead of `.corr(method="spearman")` - scipy is not a
project dependency.

    python run.py verify stability
"""

from __future__ import annotations

from checks._common import all_indicators, read_indicator

TITLE = "Company traits persist over time"
KIND = "code"
EXHIBIT = "E"
MIN_OVERLAP = 100


def run() -> dict:
    series: dict[str, list[dict]] = {}

    for ind in all_indicators():
        df = read_indicator(ind["path"])
        if df is None or df.empty:
            continue
        wide = df.pivot_table(index="ticker", columns="year", values="value")
        points = []
        for y in sorted(wide.columns):
            if y - 1 not in wide.columns:
                continue
            pair = wide[[y - 1, y]].dropna()
            if len(pair) < MIN_OVERLAP:
                continue
            rho = pair[y - 1].rank().corr(pair[y].rank())
            points.append({"year": int(y), "rho": round(float(rho), 3), "n": int(len(pair))})
        if points:
            series[ind["indicator_id"]] = points

    if not series:
        return {
            "status": "flagged",
            "verdict": f"No indicator yet has 2 consecutive years with >= {MIN_OVERLAP} companies in both.",
            "numbers": {"series": {}},
            "rows": [],
        }

    all_points = [p for pts in series.values() for p in pts]
    avg = sum(p["rho"] for p in all_points) / len(all_points)
    status = "passed" if avg >= 0.5 else "flagged"
    verdict = f"Average year-to-year rank correlation across indicators with enough overlap: {avg:.2f}."
    return {"status": status, "verdict": verdict, "numbers": {"series": series}, "rows": []}
