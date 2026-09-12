"""Shared helper: quarterly revenue and federal contract obligations per company.

This is the fetch logic behind `federal_contract_exposure.py`, split out because it
was first proven on a curated ~30-name subset (see git history, commit message
"[infra] explore federal contract concentration risk score") before being scaled to
the full S&P 500. Two live sources, no API key for either:

  revenue       data.sec.gov XBRL companyconcept, bucketed by real (start, end)
                dates - not by SEC's own fy/fp tags, which are not reliable period
                labels (see `fetch_quarterly_revenue`).
  obligations   api.usaspending.gov spending_over_time, grouped by MONTH and
                converted from federal fiscal months to calendar quarters (see
                `fetch_monthly_federal_obligations`).

Three real bugs were found and fixed getting this far - each confirmed against live
API responses, not assumed:

1. SEC's own fy/fp tags are not real period labels. A single 10-Q repeats the same
   fy/fp tag for its prior-year comparative figures, so grouping by (fy, fp) silently
   mixes two different real periods. Fixed by bucketing on the actual (start, end)
   dates instead, deduplicated by most-recent `filed` (restatements win).
2. USASpending's own "quarter" grouping is federal-fiscal, not calendar (federal FY
   Q1 = Oct-Dec). A calendar-year company's SEC quarter and USASpending's
   same-numbered quarter are a full quarter apart. Fixed by requesting "month"
   grouping and re-bucketing into real calendar quarters ourselves.
3. `recipient_search_text` is not fuzzy/tokenized despite USASpending's own docs.
   It phrase-matches against the stored name field: "IBM" and "CARDINAL HEALTH INC"
   return $0 every quarter (silent false negative) while "INTERNATIONAL BUSINESS
   MACHINES" and "CARDINAL HEALTH" (same companies, no trailing legal-form word)
   return real dollars. Fixed by searching on SEC's EDGAR legal name with the
   trailing legal-form suffix and state-of-incorporation tag stripped
   (`clean_recipient_name`).

Not an indicator - the leading underscore keeps `python run.py build` from running it.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

from common.io import http_headers

# SEC appends a state-of-incorporation or reincorporation tag in several spellings -
# "/DE/" (both slashes), "/DE" or "/MN" (closing slash omitted), "/NEW/" or "/NEW"
# (reincorporated, not a state code). All of them are 2-3 letters between slash(es)
# at the very end of the name.
_STATE_SUFFIX_RE = re.compile(r"\s*/[A-Z]{2,3}/?\s*$")
_LEGAL_SUFFIX_RE = re.compile(
    r"[,.]?\s*\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LLC|LTD|LIMITED|PLC|GROUP|HOLDINGS?)\.?\s*$",
    re.IGNORECASE,
)


def clean_recipient_name(name: str) -> str:
    name = _STATE_SUFFIX_RE.sub("", name)
    while True:
        stripped = _LEGAL_SUFFIX_RE.sub("", name).strip()
        if stripped == name.strip():
            return stripped
        name = stripped


SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_TAGS = [
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
]
USASPENDING_URL = "https://api.usaspending.gov/api/v2/search/spending_over_time/"
AUTOCOMPLETE_URL = "https://api.usaspending.gov/api/v2/autocomplete/recipient/"

# Words too generic to prove a name match by themselves (a corporate suffix or a
# common business word, not something distinctive to one company).
_FILLER_TOKENS = {
    "THE", "AND", "OF", "CORP", "CORPORATION", "INC", "INCORPORATED", "CO", "COMPANY",
    "GROUP", "HOLDINGS", "HOLDING", "LLC", "LTD", "LIMITED", "PLC", "NATIONAL",
    "AMERICAN", "GENERAL", "UNITED", "INTERNATIONAL", "GLOBAL", "INDUSTRIES",
    "SYSTEMS", "SERVICES", "TECHNOLOGIES", "TECHNOLOGY", "SOLUTIONS", "ENTERPRISES",
}


def _distinctive_tokens(name: str) -> set[str]:
    return {t for t in re.findall(r"[A-Z0-9]+", name.upper()) if len(t) >= 2 and t not in _FILLER_TOKENS}


def verify_recipient_name(search_name: str, cache_dir: Path) -> tuple[bool, str]:
    """True if USASpending's own recipient autocomplete surfaces a plausible match.

    `recipient_search_text` (used by fetch_monthly_federal_obligations) does not do
    phrase or fuzzy matching - it matches short/generic names as a raw substring
    against ANY recipient, including inside unrelated words (confirmed live:
    searching "PPL" - the cleaned legal name of PPL Corporation, an electric
    utility - autocompletes to "APPLIED INDUSTRIAL TECHNOLOGIES", "PATTERSON DENTAL
    SUPPLY" and dozens of others that merely contain the substring "ppl", and the
    resulting "obligations" total came to several times PPL's entire revenue). This
    checks whether the search name shares a distinctive token with at least one of
    USASpending's own autocomplete suggestions for it; if not, the obligations found
    for that company cannot be trusted and should be treated as unverified, not zero.
    """
    safe = "".join(c if c.isalnum() else "_" for c in search_name)[:40]
    cache_path = cache_dir / "autocomplete" / f"{safe}.json"
    data = _post_json_cached(AUTOCOMPLETE_URL, {"search_text": search_name, "limit": 15}, cache_path)
    results = [r["recipient_name"] for r in (data or {}).get("results", [])]
    mine = _distinctive_tokens(search_name)
    if not mine:
        return False, ""
    for r in results:
        if mine & _distinctive_tokens(r):
            return True, r
    return False, ""
QUARTER_DAYS = (75, 100)  # duration window that counts as "one quarter"
YEAR_DAYS = (350, 380)
PAUSE_S = 0.15


def _fetch_json_cached(url: str, cache_path: Path) -> dict | None:
    if cache_path.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        return None if cached is None else cached
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(url, headers=http_headers(), timeout=30)
    if r.status_code == 404:
        cache_path.write_text("null", encoding="utf-8")
        return None
    r.raise_for_status()
    cache_path.write_text(r.text, encoding="utf-8")
    time.sleep(PAUSE_S)
    return r.json()


def _post_json_cached(url: str, body: dict, cache_path: Path) -> dict | None:
    if cache_path.exists():
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        return None if "error" in data else data
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    r = requests.post(url, json=body, headers=http_headers(), timeout=30)
    if r.status_code >= 400:
        cache_path.write_text(json.dumps({"error": r.status_code, "text": r.text}), encoding="utf-8")
        return None
    r.raise_for_status()
    cache_path.write_text(r.text, encoding="utf-8")
    time.sleep(PAUSE_S)
    return r.json()


def get_sec_legal_names(cache_dir: Path) -> dict[str, str]:
    """ticker -> SEC EDGAR registrant legal name.

    USASpending indexes recipients under their legal entity name (e.g.
    "INTERNATIONAL BUSINESS MACHINES CORP"), not an informal display name. SEC's own
    ticker file gives us that legal name for free, matched by ticker.
    """
    data = _fetch_json_cached(SEC_TICKERS_URL, cache_dir / "sec_company_tickers.json")
    return {v["ticker"]: v["title"] for v in data.values()} if data else {}


def _quarter_label(end: pd.Timestamp) -> tuple[int, int]:
    return end.year, (end.month - 1) // 3 + 1


def fetch_quarterly_revenue(ticker: str, cik: int, cache_dir: Path) -> pd.DataFrame:
    """Quarterly revenue (USD) for one company, bucketed by real period dates."""
    cik10 = f"{cik:010d}"
    periods: dict[tuple[str, str], dict] = {}
    for tag in SEC_TAGS:
        cache_path = cache_dir / "sec" / f"{cik10}_{tag}.json"
        url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik10}/us-gaap/{tag}.json"
        data = _fetch_json_cached(url, cache_path)
        if not data:
            continue
        for u in data.get("units", {}).get("USD", []):
            if u.get("form") not in ("10-Q", "10-K"):
                continue
            start, end = u["start"], u["end"]
            days = (pd.to_datetime(end) - pd.to_datetime(start)).days
            if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
                kind = "Q"
            elif YEAR_DAYS[0] <= days <= YEAR_DAYS[1]:
                kind = "FY"
            else:
                continue
            key = (start, end)
            existing = periods.get(key)
            if existing is None or u["filed"] > existing["filed"]:
                periods[key] = {"val": u["val"], "filed": u["filed"], "kind": kind, "tag": tag}

    quarters = [
        {"start": pd.to_datetime(s), "end": pd.to_datetime(e), **v}
        for (s, e), v in periods.items() if v["kind"] == "Q"
    ]
    years = [
        {"start": pd.to_datetime(s), "end": pd.to_datetime(e), **v}
        for (s, e), v in periods.items() if v["kind"] == "FY"
    ]
    quarters.sort(key=lambda r: r["end"])

    have_ends = {q["end"] for q in quarters}
    for y in years:
        contained = [q for q in quarters if y["start"] <= q["start"] and q["end"] <= y["end"]]
        if len(contained) == 3 and y["end"] not in have_ends:
            q4_val = y["val"] - sum(q["val"] for q in contained)
            q4_start = max(q["end"] for q in contained)
            quarters.append(
                {"start": q4_start, "end": y["end"], "val": q4_val, "filed": y["filed"], "tag": y["tag"] + "+derived_q4"}
            )
            have_ends.add(y["end"])

    rows = []
    for q in quarters:
        year, qtr = _quarter_label(q["end"])
        rows.append((ticker, year, qtr, q["end"].date().isoformat(), q["val"], q["tag"]))
    out = pd.DataFrame(rows, columns=["ticker", "year", "quarter", "period_end", "revenue_usd", "sec_tag"])
    return out.sort_values(["year", "quarter"]).drop_duplicates(["year", "quarter"], keep="last").reset_index(drop=True)


def fetch_monthly_federal_obligations(
    ticker: str, name: str, start_date: str, end_date: str, cache_dir: Path
) -> pd.DataFrame:
    """Quarterly federal contract obligations via recipient name search, USASpending."""
    safe_name = "".join(c if c.isalnum() else "_" for c in name)[:60]
    cache_path = cache_dir / "usaspending" / f"{ticker}_{safe_name}.json"
    body = {
        "group": "month",
        "filters": {
            "recipient_search_text": [name],
            "award_type_codes": ["A", "B", "C", "D"],
            "time_period": [{"start_date": start_date, "end_date": end_date}],
        },
        "spending_level": "transactions",
    }
    data = _post_json_cached(USASPENDING_URL, body, cache_path)
    if not data:
        return pd.DataFrame(columns=["ticker", "year", "quarter", "contract_obligations_usd"])

    rows = []
    for r in data["results"]:
        fiscal_year = int(r["time_period"]["fiscal_year"])
        fiscal_month = int(r["time_period"]["month"])
        calendar_month = ((fiscal_month + 8) % 12) + 1
        calendar_year = fiscal_year - 1 if fiscal_month <= 3 else fiscal_year
        year, qtr = _quarter_label(pd.Timestamp(year=calendar_year, month=calendar_month, day=1))
        rows.append((year, qtr, r["aggregated_amount"]))
    monthly = pd.DataFrame(rows, columns=["year", "quarter", "amount"])
    quarterly = monthly.groupby(["year", "quarter"], as_index=False)["amount"].sum()
    quarterly.insert(0, "ticker", ticker)
    return quarterly.rename(columns={"amount": "contract_obligations_usd"})


def build_company_panel(
    ticker: str, name: str, cik: int, start_date: str, end_date: str, cache_dir: Path
) -> pd.DataFrame:
    revenue = fetch_quarterly_revenue(ticker, cik, cache_dir)
    obligations = fetch_monthly_federal_obligations(ticker, name, start_date, end_date, cache_dir)
    panel = revenue.merge(obligations, on=["ticker", "year", "quarter"], how="left")
    panel["contract_obligations_usd"] = panel["contract_obligations_usd"].fillna(0.0)
    panel["pct_revenue_federal_contracts"] = (
        panel["contract_obligations_usd"] / panel["revenue_usd"]
    ).where(panel["revenue_usd"] > 0)
    return panel
