"""Company size denominators (revenue, employees) so social indicators can be size-neutral.

Why this exists: AGENTS.md section 4 requires every indicator to be *size-neutral* -
"3 discrimination lawsuits" means something very different at a 2,000-person company than
at Walmart. Raw counts must be divided by a size denominator. This helper builds that
denominator table once, so each indicator script just joins against it.

What it measures: net revenue in USD per company, both per fiscal year (CY2016..CY2025)
and per quarter (CY2016Q1..CY2025Q4), plus the reported headcount where SEC has it.

Source: SEC XBRL *frames* API - one request returns the same tag+period for **all**
filers, so 503 companies cost one download, not 503.
  https://data.sec.gov/api/xbrl/frames/us-gaap/<TAG>/USD/CY2019Q1.json   (quarterly)
  https://data.sec.gov/api/xbrl/frames/us-gaap/<TAG>/USD/CY2019.json     (annual)

No single revenue tag covers the index: filers choose between the ASC 606 tags, the
legacy tags and, for banks, an interest-income tag. REVENUE_TAGS below is a measured
fallback chain - first tag that has the company for that period wins.

Run:    python social/scripts/_financials.py [--universe path/to/list.csv]
Output: social/raw/financials.csv
        (ticker, year, quarter, revenue_usd, employees, source, source_url, retrieved)
        `quarter` is "2019Q3" on quarterly rows and EMPTY on annual rows;
        `employees` is annual only.

Raw frames JSON is cached in social/raw/frames/ (several MB per tag-year).

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import cached_download, today_utc  # noqa: E402

CATEGORY = "social"
OUT = raw_dir(CATEGORY) / "financials.csv"
COLUMNS = [
    "ticker",
    "year",
    "quarter",
    "revenue_usd",
    "employees",
    "source",
    "source_url",
    "retrieved",
]

FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json"

FIRST_YEAR = 2016
LAST_YEAR = 2025

# Measured on CY2019Q1: this union reaches 463/500 S&P 500 CIKs, no single tag gets past
# 284. Order matters - the first tag that has a company for a period is the one used.
REVENUE_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",  # ASC 606, the modern default
    "Revenues",  # broad legacy tag, still used by many
    "RevenueFromContractWithCustomerIncludingAssessedTax",  # ASC 606 with sales taxes in
    "SalesRevenueNet",  # pre-2018 legacy tag, dead after the ASC 606 switch
    "InterestAndDividendIncomeOperating",  # banks report this instead of "revenue"
]

# Headcount lives in the dei taxonomy as an instantaneous fact, unit "pure".
EMPLOYEE_TAG = "EntityNumberOfEmployees"


def load_company_list(fallback: Path | None) -> list[dict]:
    """universe/sp500.csv when Arash has built it; otherwise an explicit fallback list."""
    from common.config import UNIVERSE_CSV

    if UNIVERSE_CSV.exists():
        src = UNIVERSE_CSV
    elif fallback and fallback.exists():
        src = fallback
        print(f"WARN universe/sp500.csv does not exist yet (Arash) - using {src}")
        print("WARN re-run this once the real universe lands; tickers must match it exactly.")
    else:
        raise FileNotFoundError(
            "universe/sp500.csv does not exist yet and no --universe fallback was given"
        )
    with src.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("cik")]
    print(f"company list: {src} ({len(rows)} companies)")
    return rows


def cik_to_tickers(companies: list[dict]) -> dict[int, list[str]]:
    """CIK -> tickers. One CIK can carry several tickers (GOOG/GOOGL, FOX/FOXA, NWS/NWSA)."""
    out: dict[int, list[str]] = defaultdict(list)
    for row in companies:
        out[int(row["cik"])].append(row["ticker"].strip().upper())
    return dict(out)


def periods() -> list[tuple[str, int, str]]:
    """(frames period, year, quarter-label). Annual rows carry an empty quarter label."""
    out: list[tuple[str, int, str]] = []
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        out.append((f"CY{year}", year, ""))
        for q in (1, 2, 3, 4):
            out.append((f"CY{year}Q{q}", year, f"{year}Q{q}"))
    return out


def fetch_frame(taxonomy: str, tag: str, unit: str, period: str) -> list[dict] | None:
    """One frames file, cached. None when SEC has no such frame (404) or the call fails."""
    url = FRAMES_URL.format(taxonomy=taxonomy, tag=tag, unit=unit, period=period)
    try:
        path = cached_download(url, CATEGORY, f"frames/{tag}_{unit}_{period}.json", pause_s=0.12)
        return json.loads(path.read_text(encoding="utf-8")).get("data") or []
    except Exception as exc:  # noqa: BLE001 - a missing frame must not kill the run
        print(f"  no frame {tag} {period} ({exc.__class__.__name__})")
        return None


def collect_revenue(ciks: dict[int, list[str]]) -> tuple[dict, dict]:
    """(ticker, year, quarter) -> {revenue_usd, source, source_url}, plus a per-tag tally."""
    values: dict[tuple[str, int, str], dict] = {}
    tag_hits: dict[str, int] = defaultdict(int)

    for period, year, quarter in periods():
        seen_this_period: set[str] = set()
        for tag in REVENUE_TAGS:
            url = FRAMES_URL.format(taxonomy="us-gaap", tag=tag, unit="USD", period=period)
            data = fetch_frame("us-gaap", tag, "USD", period)
            if not data:
                continue
            for rec in data:
                tickers = ciks.get(rec.get("cik"))
                if not tickers:
                    continue
                for ticker in tickers:
                    if ticker in seen_this_period:  # an earlier tag already won
                        continue
                    seen_this_period.add(ticker)
                    values[(ticker, year, quarter)] = {
                        "revenue_usd": rec["val"],
                        "source": f"SEC XBRL frames (us-gaap:{tag})",
                        "source_url": url,
                    }
                    tag_hits[tag] += 1
        label = quarter or f"{year} (annual)"
        print(f"  {label}: {len(seen_this_period)}/{sum(len(t) for t in ciks.values())}", flush=True)
    return values, dict(tag_hits)


def collect_employees(ciks: dict[int, list[str]]) -> dict[tuple[str, int], dict]:
    """(ticker, year) -> headcount. Instantaneous dei fact; the latest one in a year wins."""
    best: dict[tuple[str, int], tuple[str, dict]] = {}
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        for q in (1, 2, 3, 4):
            period = f"CY{year}Q{q}I"
            url = FRAMES_URL.format(taxonomy="dei", tag=EMPLOYEE_TAG, unit="pure", period=period)
            data = fetch_frame("dei", EMPLOYEE_TAG, "pure", period)
            if not data:
                continue
            for rec in data:
                tickers = ciks.get(rec.get("cik"))
                if not tickers or rec.get("val") in (None, 0):
                    continue
                end = rec.get("end", "")
                for ticker in tickers:
                    key = (ticker, year)
                    if key in best and best[key][0] >= end:
                        continue
                    best[key] = (end, {"employees": rec["val"], "source_url": url})
    return {k: v[1] for k, v in best.items()}


def build_rows(revenue: dict, employees: dict, retrieved: str) -> list[dict]:
    """Merge both sides. An annual row may have revenue, employees, or both."""
    keys = set(revenue) | {(t, y, "") for t, y in employees}
    rows = []
    for ticker, year, quarter in sorted(keys):
        rev = revenue.get((ticker, year, quarter), {})
        emp = employees.get((ticker, year), {}) if quarter == "" else {}
        rows.append(
            {
                "ticker": ticker,
                "year": year,
                "quarter": quarter,
                "revenue_usd": rev.get("revenue_usd", ""),
                "employees": emp.get("employees", ""),
                "source": rev.get("source") or f"SEC XBRL frames (dei:{EMPLOYEE_TAG})",
                "source_url": rev.get("source_url") or emp.get("source_url", ""),
                "retrieved": retrieved,
            }
        )
    return rows


def report(rows: list[dict], total: int, tag_hits: dict[str, int]) -> None:
    """Everything printed here is counted from the rows actually written."""
    annual = [r for r in rows if not r["quarter"] and r["revenue_usd"] != ""]
    quarterly = [r for r in rows if r["quarter"]]

    print("\nrevenue coverage, annual (tickers with a value / %d):" % total)
    per_year = defaultdict(set)
    for r in annual:
        per_year[r["year"]].add(r["ticker"])
    for year in sorted(per_year):
        n = len(per_year[year])
        print(f"  CY{year}: {n:3d}  ({100 * n / total:.0f}%)")

    print("\nrevenue coverage, quarterly (tickers with a value / %d):" % total)
    per_q = defaultdict(set)
    for r in quarterly:
        per_q[r["quarter"]].add(r["ticker"])
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        cells = " ".join(f"Q{q}:{len(per_q.get(f'{year}Q{q}', ())):3d}" for q in (1, 2, 3, 4))
        print(f"  {year}  {cells}")

    print("\nrevenue tag usage (how often each fallback step was the one that hit):")
    for tag in REVENUE_TAGS:
        print(f"  {tag}: {tag_hits.get(tag, 0)}")

    emp = [r for r in rows if r["employees"] != ""]
    emp_tickers = {r["ticker"] for r in emp}
    print(f"\nemployees: {len(emp)} rows, {len(emp_tickers)}/{total} tickers "
          f"({100 * len(emp_tickers) / total:.0f}%)")
    if len(emp_tickers) < 0.7 * total:
        print("  WARN dei:EntityNumberOfEmployees is barely tagged - treat `employees` as")
        print("  WARN incomplete and normalise per revenue instead. Nothing was estimated.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", type=Path, default=None, help="fallback company list CSV")
    args = ap.parse_args()

    companies = load_company_list(args.universe)
    ciks = cik_to_tickers(companies)
    total = sum(len(t) for t in ciks.values())
    print(f"{len(ciks)} distinct CIKs for {total} tickers")

    print(f"\nrevenue: {len(REVENUE_TAGS)} tags x {len(periods())} periods")
    revenue, tag_hits = collect_revenue(ciks)

    print("\nemployees: dei:EntityNumberOfEmployees, instantaneous frames")
    employees = collect_employees(ciks)

    rows = build_rows(revenue, employees, today_utc())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    print(f"\nwrote {OUT.relative_to(ROOT).as_posix()}: {len(rows)} rows, "
          f"{len({r['ticker'] for r in rows})} tickers")
    report(rows, total, tag_hits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
