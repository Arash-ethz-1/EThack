"""labor_litigation_intensity - employment lawsuits filed against a company, size-adjusted.

What it measures: how often employees sue a company over how it treated them. Federal
civil cases carry a Nature-of-Suit code; codes 442 (Civil Rights: Jobs), 445 (Disabilities
- Employment), 710 (Fair Labor Standards), 720 (Labor/Mgmt), 740 (Railway Labor), 751
(Family and Medical Leave), 790 (Other Labor) and 791 (ERISA) all mean exactly that.
Normalised per $1bn of revenue so big employers do not lose by being big. Lower is better.

Source: CourtListener RECAP (federal dockets) + SEC XBRL (revenue denominator)
Run:    python social/scripts/_dockets.py      # slow download, once
        python run.py build social labor_litigation_intensity

Output: social/indicators/labor_litigation_intensity.csv  (annual, the committed format)
        social/raw/labor_litigation_panel.csv             (quarterly, pending the
                                                           `quarter` column proposal)
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import today_utc, write_indicator  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dockets import WINDOW_FROM, WINDOW_TO, is_labor, party_matches  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "labor_litigation_intensity"
SOURCE = "CourtListener RECAP federal dockets"
SOURCE_URL = "https://www.courtlistener.com/api/rest/v4/search/"

# Bulk dump (all 503 companies) is the source; the API pull in raw/dockets/ stays as the
# validation set. Measured on the 30 overlapping companies: case-name matching recovers
# 90% of the dockets party matching found (631 vs 698), for 444/503 companies instead of 33.
DOCKETS_DIR = raw_dir(CATEGORY) / "dockets_bulk"
DOCKETS_API_DIR = raw_dir(CATEGORY) / "dockets"
# universe/financials.csv is the team's shared denominator (owner: Arash) and wins where
# it has data. It currently starts at 2019, so social/raw/financials.csv - same SEC XBRL
# frames method - fills 2016-2018 to keep the full 10-year window.
FINANCIALS_SHARED = ROOT / "universe" / "financials.csv"
FINANCIALS_LOCAL = raw_dir(CATEGORY) / "financials.csv"
PANEL_OUT = raw_dir(CATEGORY) / "labor_litigation_panel.csv"

YEAR_FROM, YEAR_TO = int(WINDOW_FROM[:4]), int(WINDOW_TO[:4]) - 1
ROLLING_QUARTERS = 4  # trailing window: one-quarter counts are mostly zero


def _read_revenue(path: Path) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    if not path.exists():
        return out
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("quarter"):  # annual rows only
                continue
            try:
                rev = float(r["revenue_usd"])
            except (TypeError, ValueError):
                continue
            if rev > 0:
                out[(r["ticker"].strip().upper(), int(r["year"]))] = rev
    return out


def load_revenue() -> dict[tuple[str, int], float]:
    """(ticker, year) -> annual revenue USD. Shared file wins; local fills earlier years."""
    revenue = _read_revenue(FINANCIALS_LOCAL)
    shared = _read_revenue(FINANCIALS_SHARED)
    revenue.update(shared)  # Arash's numbers win on any overlap
    if not revenue:
        raise SystemExit(
            "no revenue denominator found - need universe/financials.csv (Arash) or run "
            "social/scripts/_financials.py.\nAGENTS.md section 4 requires size-neutral values."
        )
    print(f"revenue: {len(shared)} rows from universe/financials.csv, "
          f"{len(revenue) - len(shared)} additional from social/raw/financials.csv")
    return revenue


def count_dockets() -> tuple[dict, dict]:
    """Labor dockets per (ticker, year) and per (ticker, 'YYYYQn'), from the raw cache."""
    per_year: dict[tuple[str, int], int] = defaultdict(int)
    per_quarter: dict[tuple[str, str], int] = defaultdict(int)
    for path in sorted(DOCKETS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        ticker, names = data["ticker"], data["names"]
        for d in data["dockets"]:
            filed = d.get("dateFiled") or ""
            if len(filed) < 10 or not (WINDOW_FROM <= filed < WINDOW_TO):
                continue
            if not is_labor(d.get("suitNature")):
                continue
            # Bulk rows were already matched to this company during extraction and carry
            # no party list; API rows still need the party check.
            if data.get("source") != "bulk" and not party_matches(d.get("party"), names):
                continue
            year = int(filed[:4])
            per_year[(ticker, year)] += 1
            per_quarter[(ticker, f"{year}Q{(int(filed[5:7]) - 1) // 3 + 1}")] += 1
    return per_year, per_quarter


def build() -> pd.DataFrame:
    revenue = load_revenue()
    per_year, per_quarter = count_dockets()
    tickers = sorted({t for t, _ in per_year} | {t for t, _ in revenue})

    # Annual: suits filed that year per $1bn of that year's revenue. A company we
    # downloaded with no suits is a real zero; a company with no revenue is a missing row.
    rows = []
    for ticker in tickers:
        if not (DOCKETS_DIR / f"{ticker}.json").exists():
            continue
        for year in range(YEAR_FROM, YEAR_TO + 1):
            rev = revenue.get((ticker, year))
            if not rev:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "year": year,
                    "value": round(per_year.get((ticker, year), 0) / (rev / 1e9), 4),
                    "source": SOURCE,
                    "source_url": SOURCE_URL,
                    "retrieved": today_utc(),
                    "note": f"{per_year.get((ticker, year), 0)} labor dockets / "
                            f"${rev / 1e9:.1f}bn revenue",
                }
            )
    write_panel(per_quarter, revenue, tickers)
    return pd.DataFrame(rows)


def write_panel(per_quarter: dict, revenue: dict, tickers: list[str]) -> None:
    """Quarterly panel: trailing 4-quarter suits per $1bn revenue.

    A single quarter is mostly zeros, which would collapse the percentile ranks, so the
    value at quarter Q is the sum over Q-3..Q.
    """
    quarters = [f"{y}Q{q}" for y in range(YEAR_FROM, YEAR_TO + 1) for q in (1, 2, 3, 4)]
    rows = []
    for ticker in tickers:
        if not (DOCKETS_DIR / f"{ticker}.json").exists():
            continue
        for i, quarter in enumerate(quarters):
            if i < ROLLING_QUARTERS - 1:
                continue
            window = quarters[i - ROLLING_QUARTERS + 1 : i + 1]
            rev = revenue.get((ticker, int(quarter[:4])))
            if not rev:
                continue
            rows.append(
                {
                    "ticker": ticker,
                    "quarter": quarter,
                    "year": int(quarter[:4]),
                    "value": round(sum(per_quarter.get((ticker, q), 0) for q in window)
                                   / (rev / 1e9), 4),
                    "source": SOURCE,
                    "source_url": SOURCE_URL,
                    "retrieved": today_utc(),
                    "note": f"trailing {ROLLING_QUARTERS}q",
                }
            )
    PANEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(PANEL_OUT, index=False, lineterminator="\n")
    n_t = len({r["ticker"] for r in rows})
    print(f"wrote {PANEL_OUT.name}: {len(rows)} rows, {n_t} tickers, "
          f"{len({r['quarter'] for r in rows})} quarters (trailing {ROLLING_QUARTERS}q)")


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
