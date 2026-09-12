"""Build universe/financials.csv - revenue and employees, the shared size denominators.

Owner:  Arash
Source: revenue   - SEC XBRL frames API (one call per tag and calendar year, all filers)
        employees - the headcount sentence in each company's 10-K ("As of December 31,
                    2025, we employed approximately 57,000 people"). Not tagged in XBRL.
Run:    python universe/build_financials.py                  revenue + employees (slow, resumable)
        python universe/build_financials.py --skip-employees revenue only (1 minute)

Output: universe/financials.csv - one row per ticker + year:
        ticker, year, revenue_usd, employees, revenue_source_url, revenue_note,
        employees_source_url, employees_note
Not an indicator and not scored. Missing value = empty cell, never estimated.

Year = the calendar year that contains most of the fiscal year (fiscal year ending
Jan 2026 -> 2025, Sep 2025 -> 2025), the same rule the SEC frames API uses.

Employees are extracted with a strict pattern only (had/employed/workforce of + number +
employees/people/associates...). Subsets (union members, U.S. only, "72,000 employees,
or 40% of our workforce") are rejected; companies that state headcount only in a table
get no value. Every value keeps the exact quote in employees_note.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import requests

from common.config import ROOT, raw_dir
from common.io import http_headers, load_universe, today_utc

AREA = "universe"
OUT = ROOT / "universe" / "financials.csv"
YEARS = range(2019, 2026)

# Total revenue tags: a company's revenue is the largest of these (each is at most the total).
TOTAL_REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
]
# Used only when none of the above exists (banks, utilities), in this order.
FALLBACK_REVENUE_TAGS = [
    "RevenuesNetOfInterestExpense",
    "RegulatedAndUnregulatedOperatingRevenue",
    "ElectricUtilityRevenue",
    "InterestAndDividendIncomeOperating",
]
FRAMES_URL = "https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/CY{year}.json"

EMPLOYEE_YEARS = range(2021, 2026)  # 10-Ks for these fiscal years
EMPLOYEES_RAW = raw_dir(AREA) / "employees_10k.csv"
EMPLOYEES_RAW_COLUMNS = ["ticker", "cik", "accession", "period_end", "year", "employees", "quote", "url", "retrieved"]

_lock = threading.Lock()
_last_request = [0.0]


def sec_get(url: str) -> requests.Response:
    """GET with the SEC contact header, max ~8 requests/second across all threads."""
    with _lock:
        wait = 0.125 - (time.monotonic() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()
    for attempt in range(4):
        resp = requests.get(url, headers=http_headers(), timeout=120)
        if resp.status_code not in (429, 503):
            return resp
        time.sleep(2 * (attempt + 1))
    return resp


def log_download(filename: str, url: str, n_bytes: int) -> None:
    log = raw_dir(AREA) / "_downloads.csv"
    new = not log.exists()
    with _lock, log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["file", "url", "retrieved_utc", "bytes"])
        w.writerow([filename, url, dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), n_bytes])


def fiscal_year(period_end: str) -> int:
    return (pd.Timestamp(period_end) - pd.Timedelta(days=182)).year


# ---------------------------------------------------------------- revenue
def download_revenue_frames(ciks: set[int], refresh: bool = False) -> pd.DataFrame:
    """All frames for our tags and years, filtered to the universe -> universe/raw/revenue_frames.csv."""
    path = raw_dir(AREA) / "revenue_frames.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, dtype={"accn": str})
    rows = []
    for tag in TOTAL_REVENUE_TAGS + FALLBACK_REVENUE_TAGS:
        for year in YEARS:
            url = FRAMES_URL.format(tag=tag, year=year)
            resp = sec_get(url)
            if resp.status_code == 404:  # tag not used by anyone that year
                continue
            resp.raise_for_status()
            log_download(f"revenue_frames.csv <- {tag} CY{year}", url, len(resp.content))
            for d in resp.json()["data"]:
                if d["cik"] in ciks:
                    rows.append({"tag": tag, "year": year, "cik": d["cik"], "start": d["start"],
                                 "end": d["end"], "val": d["val"], "accn": d["accn"], "url": url})
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, lineterminator="\n")
    return df


def revenue_table(universe: pd.DataFrame, refresh: bool = False) -> pd.DataFrame:
    ciks = universe.assign(cik_int=universe["cik"].astype(int))
    frames = download_revenue_frames(set(ciks["cik_int"]), refresh=refresh)
    frames = frames[frames["val"] > 0]
    total = frames[frames["tag"].isin(TOTAL_REVENUE_TAGS)]
    best_total = total.sort_values("val").groupby(["cik", "year"]).tail(1)
    fallback = frames[frames["tag"].isin(FALLBACK_REVENUE_TAGS)].copy()
    fallback["prio"] = fallback["tag"].map(FALLBACK_REVENUE_TAGS.index)
    best_fallback = fallback.sort_values("prio").groupby(["cik", "year"]).head(1)
    best_fallback = best_fallback.merge(best_total[["cik", "year"]], how="left", indicator=True)
    best_fallback = best_fallback[best_fallback["_merge"] == "left_only"].drop(columns=["_merge", "prio"])
    best = pd.concat([best_total, best_fallback], ignore_index=True)

    best = best.merge(ciks[["ticker", "cik_int"]], left_on="cik", right_on="cik_int")
    return pd.DataFrame({
        "ticker": best["ticker"],
        "year": best["year"].astype(int),
        "revenue_usd": best["val"].astype("int64"),
        "revenue_source_url": best["url"],
        "revenue_note": "us-gaap:" + best["tag"] + " " + best["start"] + ".." + best["end"] + " accn " + best["accn"],
    })


# ---------------------------------------------------------------- employees
NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?\s*(?:thousand|million)|\d{2,7})"
NOUN = r"(?:employees|associates|team members|teammates|colleagues|people|staff|workers|full[- ]time equivalents?)"
HEADCOUNT = re.compile(
    r"\b(?:had|have|employed|employs|employ|employing|workforce (?:of|was|totaled|consisted of)|"
    r"a total of|totaled|consisted of|global team of|team of)\s+"
    r"(?:(?:a total of|approximately|about|over|more than|nearly|roughly|just over|around|some)\s+)*"
    + NUM + r"\s+(?:[A-Za-z][A-Za-z-]*\s+){0,5}?" + NOUN + r"\b",
    re.I,
)
# Number is a subset of the workforce, not the total.
SUBSET_BEFORE = re.compile(
    r"represent|union|collective|bargain|tenure|years of service|hours|train|volunteer|hired|hires|"
    r"contract|temporar|seasonal|intern|retire|former|women|veteran|customers|patients|of whom|including|"
    r"segment|division",
    re.I,
)
SUBSET_AFTER = re.compile(
    r"\W*(?:or |and |were |are )?(?:approximately )?\d+(?:\.\d+)?\s*(?:%|percent)|"
    r"\W*(?:who |that )?(?:are |were )?(?:represented|covered by|located in|based in|in the (?:United States|U\.S))",
    re.I,
)


def number(text: str) -> int:
    m = re.match(r"([\d.]+)\s*(thousand|million)?", text.lower().replace(",", "").strip())
    return int(round(float(m.group(1)) * {"thousand": 1e3, "million": 1e6}.get(m.group(2), 1)))


def plain_text(raw_html: str) -> str:
    t = re.sub(r"(?is)<(script|style|ix:header)\b.*?</\1>", " ", raw_html)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t))


def extract_employees(text: str) -> tuple[int, str] | None:
    """First strict headcount sentence that is not a subset. None if there is none."""
    for m in HEADCOUNT.finditer(text):
        clause = re.split(r"[.;]\s", text[max(0, m.start() - 120) : m.start()])[-1]
        if SUBSET_BEFORE.search(clause) or SUBSET_BEFORE.search(m.group(0)):
            continue
        if SUBSET_AFTER.match(text[m.end() : m.end() + 60]):
            continue
        value = number(m.group(1))
        if not 50 <= value <= 3_000_000 or ("," not in m.group(1) and 1990 <= value <= 2035):
            continue
        quote = text[max(0, m.start() - 80) : m.end() + 40].strip()
        return value, quote
    return None


def list_10ks(cik: str) -> list[dict]:
    """Annual reports (form 10-K) with period end, newest first, from the SEC submissions API."""
    base = "https://data.sec.gov/submissions/"
    sub = sec_get(f"{base}CIK{cik}.json").json()
    pages = [pd.DataFrame(sub["filings"]["recent"])]
    for extra in sub["filings"].get("files", []):
        if extra["filingTo"] >= f"{min(EMPLOYEE_YEARS)}-01-01":
            pages.append(pd.DataFrame(sec_get(base + extra["name"]).json()))
    f = pd.concat(pages, ignore_index=True)
    f = f[(f["form"] == "10-K") & (f["reportDate"] != "")]
    out = []
    for _, r in f.iterrows():
        year = fiscal_year(r["reportDate"])
        if year in EMPLOYEE_YEARS:
            url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{r['accessionNumber'].replace('-', '')}/{r['primaryDocument']}"
            out.append({"accession": r["accessionNumber"], "period_end": r["reportDate"], "year": year, "url": url})
    return out


def employees_for_company(ticker: str, cik: str, done: set[str]) -> list[dict]:
    rows = []
    try:
        filings = list_10ks(cik)
    except Exception as e:  # noqa: BLE001 - one broken company must not stop 500 others
        print(f"  WARN {ticker}: filing list failed ({e})", flush=True)
        return rows
    for f in filings:
        if f["accession"] in done:
            continue
        resp = sec_get(f["url"])
        if resp.status_code != 200:
            print(f"  WARN {ticker} {f['year']}: HTTP {resp.status_code} {f['url']}", flush=True)
            continue
        hit = extract_employees(plain_text(resp.text))
        rows.append({"ticker": ticker, "cik": cik, **f, "employees": hit[0] if hit else "",
                     "quote": hit[1] if hit else "", "retrieved": today_utc()})
    return rows


def download_employees(universe: pd.DataFrame, workers: int = 4) -> pd.DataFrame:
    """Resumable: filings already in universe/raw/employees_10k.csv are skipped."""
    done: set[str] = set()
    if EMPLOYEES_RAW.exists():
        done = set(pd.read_csv(EMPLOYEES_RAW, dtype=str)["accession"])
    else:
        EMPLOYEES_RAW.parent.mkdir(parents=True, exist_ok=True)
        with EMPLOYEES_RAW.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f, lineterminator="\n").writerow(EMPLOYEES_RAW_COLUMNS)

    counter = [0]

    def work(row) -> None:
        rows = employees_for_company(row.ticker, row.cik, done)
        with _lock:
            with EMPLOYEES_RAW.open("a", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=EMPLOYEES_RAW_COLUMNS, lineterminator="\n")
                w.writerows(rows)
            counter[0] += 1
            if counter[0] % 25 == 0:
                print(f"  employees: {counter[0]}/{len(universe)} companies", flush=True)

    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(work, universe.itertuples()))
    return pd.read_csv(EMPLOYEES_RAW, dtype={"cik": str, "accession": str})


def employees_table(raw: pd.DataFrame) -> pd.DataFrame:
    raw = raw.dropna(subset=["employees"])
    # an amended or re-filed 10-K for the same year: keep the latest filing
    raw = raw.sort_values("accession").groupby(["ticker", "year"]).tail(1)
    return pd.DataFrame({
        "ticker": raw["ticker"],
        "year": raw["year"].astype(int),
        "employees": raw["employees"].astype("int64"),
        "employees_source_url": raw["url"],
        "employees_note": "10-K period end " + raw["period_end"] + ': "' + raw["quote"].str.replace('"', "'") + '"',
    })


# ---------------------------------------------------------------- main
def main() -> None:
    universe = load_universe()
    rev = revenue_table(universe, refresh="--refresh" in sys.argv)
    for y in sorted(rev["year"].unique()):
        print(f"revenue {y}: {rev.loc[rev['year'] == y, 'ticker'].nunique()}/{len(universe)} companies")

    if "--skip-employees" in sys.argv:
        emp = pd.DataFrame(columns=["ticker", "year", "employees", "employees_source_url", "employees_note"])
        if EMPLOYEES_RAW.exists():
            emp = employees_table(pd.read_csv(EMPLOYEES_RAW, dtype={"cik": str, "accession": str}))
    else:
        emp = employees_table(download_employees(universe))
    for y in sorted(emp["year"].unique()):
        print(f"employees {y}: {emp.loc[emp['year'] == y, 'ticker'].nunique()}/{len(universe)} companies")

    out = rev.merge(emp, on=["ticker", "year"], how="outer")
    out = out[out["ticker"].isin(universe["ticker"])]
    out["employees"] = out["employees"].astype("Int64")
    out["revenue_usd"] = out["revenue_usd"].astype("Int64")
    cols = ["ticker", "year", "revenue_usd", "employees", "revenue_source_url", "revenue_note",
            "employees_source_url", "employees_note"]
    out = out[cols].sort_values(["ticker", "year"]).reset_index(drop=True)
    out.to_csv(OUT, index=False, lineterminator="\n")
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}: {len(out)} rows, {out['ticker'].nunique()} tickers")


if __name__ == "__main__":
    main()
