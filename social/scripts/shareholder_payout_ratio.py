"""shareholder_payout_ratio - cash handed to shareholders as a share of the cash the business generates.

What it measures: (share buybacks + dividends paid) / net cash from operating activities,
per fiscal year. It is the share of self-generated cash that leaves the company for its
owners instead of staying inside it, where it could pay wages, training, headcount, safety
and capability. This is the classic "financialisation" critique and it maps onto the
shareholder-versus-stakeholder balance that frameworks such as JUST Capital treat as a core
stakeholder dimension. Higher = worse.

Source: SEC XBRL *frames* API - one request returns one tag for one period for **all**
filers, so 503 companies cost one download, not 503.
  https://data.sec.gov/api/xbrl/frames/us-gaap/<TAG>/USD/CY2019.json    (annual)
  https://data.sec.gov/api/xbrl/frames/us-gaap/<TAG>/USD/CY2019Q1.json  (quarterly)

No single tag covers the index, so each of the three components has a *measured* fallback
chain (see BUYBACK_TAGS / DIVIDEND_TAGS / OCF_TAGS below); the first tag that has the
company for that period wins, and every chain step is there because it added companies no
earlier step had.

Rules, applied honestly (AGENTS.md 4.6 - never invent, estimate or interpolate):

* **Operating cash flow decides whether a row exists.** No OCF fact for that company-year
  -> no row. We never fill it in.
* **No buyback line and no dividend line is a real zero**, not missing data. A cash flow
  statement that does not carry the line item is a company that did not do it. Because all
  three components come out of the same cash flow statement, a company whose OCF is in a
  frame would also be in that frame for buybacks/dividends if it had tagged them.
* **A zero that is contradicted is dropped, not published.** The frames API only serves
  facts carrying no dimensional qualifier, so a filer that splits dividends by share class
  has no dividend fact in the frame at all. Every zero is therefore cross-checked against
  us-gaap:CommonStockDividendsPerShareCashPaid / us-gaap:TreasuryStockSharesAcquired; if
  the company demonstrably did pay or repurchase that year, the row is dropped because we
  cannot measure the amount. Measured: 25 dividend and 7 buyback rows, 8 tickers.
* **Only facts covering exactly the same period as the OCF fact are used.** If a company
  tagged buybacks for a different duration than its OCF fact, the row is dropped rather
  than mixing periods or silently reading it as zero.
* **Non-positive operating cash flow -> no row.** "Share of the cash the business
  generates" is undefined when the business generated none; the ratio would flip sign or
  explode. Cash-burning years are omitted, not clipped.
* **Ratio above MAX_RATIO (10x) -> no row.** Those are near-zero-OCF years where the
  denominator, not the payout, drives the number. Omitted, not winsorised - nothing is
  clipped into range and no infinity is ever emitted.
* Dividends to **minority/noncontrolling interests are excluded** - that cash goes to the
  outside owners of subsidiaries, not to this company's shareholders.

Run:    python run.py build social shareholder_payout_ratio

Output: social/indicators/shareholder_payout_ratio.csv  (annual 2016-2025, committed format)
        social/raw/shareholder_payout_panel.csv         (quarterly 2016Q1-2025Q4, pending
                                                         the `quarter` column proposal)

A note on the quarterly panel, measured not assumed: cash flow statements are reported
**cumulative year-to-date**, so a 10-Q for fiscal Q2 carries a six-month duration and a
fiscal-Q3 10-Q a nine-month one. The frames API matches facts to a calendar quarter by
duration, so those never land in a quarterly frame. Measured on
NetCashProvidedByUsedInOperatingActivities: CY2023Q1 holds 5,350 facts across all filers
(403 of our tickers) but CY2023Q2 only 394 (30 of ours) and CY2023Q4 only 43 of ours - each
company contributes at most its own *fiscal* Q1. A genuine quarter-by-quarter payout ratio
therefore does not exist in XBRL. The panel consequently carries the fiscal-year ratio held
flat across that fiscal year's four quarters, which every row says in its `note`. Nothing is
interpolated or smoothed: it is the same audited annual number, repeated and labelled.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, UNIVERSE_CSV, raw_dir  # noqa: E402
from common.io import cached_download, today_utc, write_indicator  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "shareholder_payout_ratio"
SOURCE = "SEC XBRL frames (cash flow statement)"  # each row carries its own frame URL

FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/{unit}/{period}.json"
PANEL_OUT = raw_dir(CATEGORY) / "shareholder_payout_panel.csv"

FIRST_YEAR = 2016
LAST_YEAR = 2025

# A payout of more than 10x the cash the business generated is a denominator artefact, not
# a payout policy. Those rows are dropped (see the docstring); nothing is clipped.
MAX_RATIO = 10.0

# Measured fallback chains. The count after each tag is the S&P 500 tickers it reached on
# its own in CY2024, then how many of those no earlier step in the chain had. Every step
# below earns its place; the tags that added nothing were dropped. First tag that has the
# company for the period wins.
BUYBACK_TAGS = [
    "PaymentsForRepurchaseOfCommonStock",  # 417 - the cash flow statement default
    "PaymentsForRepurchaseOfEquity",  # 7, adds 5 - used when common + preferred are merged
    "TreasuryStockValueAcquiredCostMethod",  # 190, adds 5
    "StockRepurchasedDuringPeriodValue",  # 86, adds 3 - equity statement, same annual period
    "StockRepurchasedAndRetiredDuringPeriodValue",  # 110, adds 1
    "PaymentsForRepurchaseOfOtherEquity",  # 5, adds 0 in CY2024 but 2 in CY2017
]
DIVIDEND_TAGS = [
    "PaymentsOfDividendsCommonStock",  # 244 - cleanest: common shareholders only
    "PaymentsOfDividends",  # 151, adds 141 - all classes, used when nothing is split out
    "PaymentsOfOrdinaryDividends",  # 24, adds 17 - the only dividend tag J&J and others use
    "PaymentsOfDividendsPreferredStockAndPreferenceStock",  # 40, adds 2
]
# Deliberately NOT in the dividend chain:
#   PaymentsOfDividendsMinorityInterest    - cash to the outside owners of consolidated
#                                            subsidiaries, not to this company's shareholders
#   PaymentsOfDistributionsToAffiliates    - same reason (adds 1)
#   PaymentsOfCapitalDistribution          - return of capital, not a dividend (adds 1)
OCF_TAGS = [
    "NetCashProvidedByUsedInOperatingActivities",  # 494
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",  # 47, adds 6
]

# Never used as a value - used to catch false zeros. The frames API only serves facts with
# no dimensional qualifier, so a filer that tags dividends split by share class has no
# dividend fact in the frame at all and would otherwise be read as "paid nothing". These
# per-share / per-share-count tags say whether the company did pay or repurchase that year;
# when they contradict a zero we read, the row is dropped rather than published wrong.
DIVIDEND_PER_SHARE_TAG = "CommonStockDividendsPerShareCashPaid"
DIVIDEND_PER_SHARE_UNIT = "USD-per-shares"
BUYBACK_SHARES_TAG = "TreasuryStockSharesAcquired"
BUYBACK_SHARES_UNIT = "shares"


# universe CIK -> the CIK that actually filed the 2016-2025 financials. A holding-company
# re-organisation moves the ticker to a brand new CIK with no filing history, so the
# universe CIK returns nothing from any frame. Only hand-verified entries belong here.
#   2115436 "ExxonMobil Holdings Corp" carries the ticker XOM but has filed no 10-K; every
#   Exxon annual report 2016-2025 is filed by 34088 "Exxon Mobil Corp".
#   Checked: https://data.sec.gov/submissions/CIK0002115436.json and CIK0000034088.json
PREDECESSOR_CIKS = {2115436: 34088}


def load_ciks() -> dict[int, list[str]]:
    """CIK -> tickers. One CIK can carry several tickers (GOOG/GOOGL, FOX/FOXA, NWS/NWSA)."""
    if not UNIVERSE_CSV.exists():
        raise SystemExit("universe/sp500.csv does not exist - nothing to join frames against")
    out: dict[int, list[str]] = defaultdict(list)
    with UNIVERSE_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not row.get("cik"):
                continue
            ticker = row["ticker"].strip().upper()
            cik = int(row["cik"])
            out[cik].append(ticker)
            if cik in PREDECESSOR_CIKS:
                out[PREDECESSOR_CIKS[cik]].append(ticker)
    return dict(out)


def fetch_frame(tag: str, period: str, unit: str = "USD") -> list[dict]:
    """One frames file, cached under social/raw/frames/. Empty when SEC has no such frame."""
    url = FRAMES_URL.format(tag=tag, unit=unit, period=period)
    try:
        path = cached_download(url, CATEGORY, f"frames/{tag}_{unit}_{period}.json", pause_s=0.12)
        return json.loads(path.read_text(encoding="utf-8")).get("data") or []
    except Exception as exc:  # noqa: BLE001 - a missing frame must not kill the run
        print(f"  no frame {tag} {period} ({exc.__class__.__name__})")
        return []


def collect(tags: list[str], period: str, ciks: dict[int, list[str]]) -> dict[str, dict]:
    """ticker -> {val, start, end, tag, url} for this period, first tag in the chain wins."""
    found: dict[str, dict] = {}
    for tag in tags:
        url = FRAMES_URL.format(tag=tag, unit="USD", period=period)
        for rec in fetch_frame(tag, period):
            for ticker in ciks.get(rec.get("cik"), ()):
                if ticker in found or rec.get("val") is None:
                    continue
                found[ticker] = {
                    "val": float(rec["val"]),
                    "start": rec.get("start", ""),
                    "end": rec.get("end", ""),
                    "tag": tag,
                    "url": url,
                }
    return found


def collect_matching(tags: list[str], period: str, ciks: dict[int, list[str]]) -> dict[str, dict]:
    """Like collect(), but keeps every tag hit per ticker so the caller can match periods."""
    found: dict[str, list[dict]] = defaultdict(list)
    for tag in tags:
        url = FRAMES_URL.format(tag=tag, unit="USD", period=period)
        for rec in fetch_frame(tag, period):
            for ticker in ciks.get(rec.get("cik"), ()):
                if rec.get("val") is None:
                    continue
                found[ticker].append(
                    {
                        "val": float(rec["val"]),
                        "start": rec.get("start", ""),
                        "end": rec.get("end", ""),
                        "tag": tag,
                        "url": url,
                    }
                )
    return dict(found)


def pick(hits: list[dict], start: str, end: str, tags: list[str]) -> dict | None:
    """The earliest-chain fact covering exactly the OCF fact's period, or None."""
    for tag in tags:
        for hit in hits:
            if hit["tag"] == tag and hit["start"] == start and hit["end"] == end:
                return hit
    return None


def compute(period: str, ciks: dict[int, list[str]], stats: dict) -> dict[str, dict]:
    """ticker -> the payout ratio and its audit trail for one frames period."""
    ocf = collect(OCF_TAGS, period, ciks)
    buybacks = collect_matching(BUYBACK_TAGS, period, ciks)
    dividends = collect_matching(DIVIDEND_TAGS, period, ciks)
    # cross-checks, never a value
    paid_per_share = {
        ticker
        for rec in fetch_frame(DIVIDEND_PER_SHARE_TAG, period, DIVIDEND_PER_SHARE_UNIT)
        for ticker in ciks.get(rec.get("cik"), ())
        if (rec.get("val") or 0) > 0
    }
    bought_shares = {
        ticker
        for rec in fetch_frame(BUYBACK_SHARES_TAG, period, BUYBACK_SHARES_UNIT)
        for ticker in ciks.get(rec.get("cik"), ())
        if (rec.get("val") or 0) > 0
    }
    contradicts = {"buybacks": bought_shares, "dividends": paid_per_share}

    out: dict[str, dict] = {}
    for ticker, o in ocf.items():
        stats["tag_ocf"][o["tag"]] += 1
        if o["val"] <= 0:
            stats["dropped_non_positive_ocf"] += 1
            continue

        parts = []
        total = 0.0
        for label, hits, tags in (
            ("buybacks", buybacks.get(ticker, []), BUYBACK_TAGS),
            ("dividends", dividends.get(ticker, []), DIVIDEND_TAGS),
        ):
            hit = pick(hits, o["start"], o["end"], tags)
            if hit is None and hits:
                # tagged, but for a different duration than the OCF fact - do not read
                # that as a zero and do not mix periods
                parts = None
                stats[f"dropped_period_mismatch_{label}"] += 1
                break
            if hit is None and ticker in contradicts[label]:
                # the company did pay/repurchase, but the frame has no undimensioned fact
                # for it - publishing a zero here would be wrong, so drop the row
                parts = None
                stats[f"dropped_false_zero_{label}"] += 1
                stats["false_zero_tickers"].add(ticker)
                break
            val = abs(hit["val"]) if hit else 0.0  # sign convention varies between filers
            if hit:
                stats[f"tag_{label}"][hit["tag"]] += 1
            else:
                stats[f"zero_{label}"] += 1
            total += val
            parts.append(f"{label} ${val / 1e9:.2f}bn")
        if parts is None:
            continue

        ratio = total / o["val"]
        if ratio > MAX_RATIO:
            stats["dropped_above_max_ratio"] += 1
            continue
        out[ticker] = {
            "value": round(ratio, 4),
            "note": f"{parts[0]} + {parts[1]} / OCF ${o['val'] / 1e9:.2f}bn"
            f" (fiscal period {o['start']}..{o['end']})",
            "source_url": o["url"],
        }
    return out


def build() -> pd.DataFrame:
    ciks = load_ciks()
    total = len({t for tickers in ciks.values() for t in tickers})
    print(f"{len(ciks)} CIKs (incl. {len(PREDECESSOR_CIKS)} predecessor) for "
          f"{total} tickers in universe/sp500.csv")

    stats: dict = defaultdict(int)
    for key in ("tag_ocf", "tag_buybacks", "tag_dividends"):
        stats[key] = defaultdict(int)
    stats["false_zero_tickers"] = set()

    retrieved = today_utc()
    rows: list[dict] = []
    by_year: dict[int, dict[str, dict]] = {}
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        result = compute(f"CY{year}", ciks, stats)
        by_year[year] = result
        for ticker, r in sorted(result.items()):
            rows.append(
                {
                    "ticker": ticker,
                    "year": year,
                    "value": r["value"],
                    "source": SOURCE,
                    "source_url": r["source_url"],
                    "retrieved": retrieved,
                    "note": r["note"],
                }
            )
        print(f"  CY{year}: {len(result):3d}/{total} tickers ({100 * len(result) / total:.0f}%)", flush=True)

    write_panel(by_year, retrieved)
    report(rows, total, stats)
    return pd.DataFrame(rows)


def write_panel(by_year: dict[int, dict[str, dict]], retrieved: str) -> None:
    """Quarterly panel: the fiscal-year ratio held flat across that year's four quarters.

    See the module docstring - SEC cash flow facts are cumulative year-to-date, so no true
    quarterly payout ratio exists in XBRL. Every row says so in its `note`.
    """
    rows = []
    for year in sorted(by_year):
        for ticker, r in sorted(by_year[year].items()):
            for q in (1, 2, 3, 4):
                rows.append(
                    {
                        "ticker": ticker,
                        "quarter": f"{year}Q{q}",
                        "year": year,
                        "value": r["value"],
                        "source": SOURCE,
                        "source_url": r["source_url"],
                        "retrieved": retrieved,
                        # the "why" is in this module's docstring; keeping it out of
                        # every row keeps the committed file small
                        "note": f"fiscal-year value held flat across the year's quarters; {r['note']}",
                    }
                )
    PANEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(PANEL_OUT, index=False, lineterminator="\n")
    print(
        f"wrote {PANEL_OUT.relative_to(ROOT).as_posix()}: {len(rows)} rows, "
        f"{len({r['ticker'] for r in rows})} tickers, {len({r['quarter'] for r in rows})} quarters"
    )


def report(rows: list[dict], total: int, stats: dict) -> None:
    """Everything printed here is counted from the rows actually written."""
    per_year = defaultdict(set)
    for r in rows:
        per_year[r["year"]].add(r["ticker"])
    print("\ncoverage, annual (tickers with a value / %d):" % total)
    worst = 1.0
    for year in sorted(per_year):
        n = len(per_year[year])
        worst = min(worst, n / total)
        print(f"  {year}: {n:3d}  ({100 * n / total:.0f}%)")

    print("\nwhich tag in each chain was the one that hit:")
    for key, tags in (("tag_ocf", OCF_TAGS), ("tag_buybacks", BUYBACK_TAGS), ("tag_dividends", DIVIDEND_TAGS)):
        print(f"  {key.removeprefix('tag_')}:")
        for tag in tags:
            print(f"    {tag}: {stats[key].get(tag, 0)}")
    print(f"  real zeros: buybacks {stats['zero_buybacks']}, dividends {stats['zero_dividends']}")


    print("\nrows omitted (never invented, never clipped):")
    for key in (
        "dropped_non_positive_ocf",
        "dropped_above_max_ratio",
        "dropped_period_mismatch_buybacks",
        "dropped_period_mismatch_dividends",
        "dropped_false_zero_buybacks",
        "dropped_false_zero_dividends",
    ):
        print(f"  {key}: {stats[key]}")
    if stats["false_zero_tickers"]:
        print(f"  false-zero tickers: {sorted(stats['false_zero_tickers'])}")

    if worst < 0.70:
        print(
            f"\n  WARN lowest yearly coverage is {100 * worst:.0f}% of {total} companies, below the "
            "70% bar in AGENTS.md section 4 - catalog status must stay 'in_progress'."
        )


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
