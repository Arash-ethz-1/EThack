"""Shared 10-K employee-headcount extraction for economic/ indicator scripts.

Not an indicator itself - imported by employment_growth.py. Self-contained: only
reads universe/sp500.csv (ticker/CIK lookup, read-only) and downloads SEC filings
directly - does NOT depend on universe/financials.csv, so it isn't blocked by
whatever state that file (owned by Arash/Jean) is in.

There is no structured (XBRL) tag for total employee headcount - it's disclosed as
prose in Item 1 "Human Capital" of the 10-K (required since 2020, Item 101(c)).

Extraction strategy, after two earlier rounds of real failures on real filings:
  1. Collect EVERY plausible "N employees/people/associates/colleagues" mention in
     the filing (several phrasings: digits or word-scale "2.1 million"/"58
     thousand", with or without "approximately", "as of <date>" or not).
  2. Drop candidates near litigation language (lawsuit/tribunal/plaintiff/...) -
     otherwise a UK equal-pay case mentioning "73,000 current and former ... store
     employees" gets picked up as if it were the workforce total.
  3. Of what's left, take the LARGEST number, not the first match. Every segment-,
     division-, subsidiary- or department-scoped headcount found so far (Caterpillar
     regional subtotal, NextEra's FPL subsidiary, Zoetis's "sales organization",
     Super Micro's "R&D organization") was smaller than the real company-wide total
     stated elsewhere in the same filing - a company-wide total is close to the sum
     of its parts, so it's essentially always the biggest number near "employees" in
     the document. This is the fix for the segment/subset trap that a fixed
     "first match" or "earliest in doc" rule kept missing in different ways.
  4. Special case: some filings state several fiscal years in one sentence
     ("... was 58 thousand, 61 thousand, and 62 thousand at years ended 2025, 2024,
     and 2023, respectively.") - trusted as-is (self-consistent, no ambiguity) and
     returned without going through the max-of-candidates step.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from common.io import cached_download, cached_json

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accn_nodash}/{doc}"

# Known-wrong CIK in universe/sp500.csv (points to a shell entity with zero 10-K
# filings - flagged to Arash separately). Worked around here, scoped to economic/
# only, so employment_growth doesn't inherit the bug while it's still unfixed
# upstream. Remove once universe/sp500.csv is corrected.
CIK_OVERRIDES = {
    "XOM": "0000034088",  # real Exxon Mobil Corporation; sp500.csv has 0002115436
}

BAD_CONTEXT = re.compile(
    r"litigation|lawsuit|tribunal|allege|claimant|plaintiff|class action|former\s",
    re.IGNORECASE,
)

_NUM = r"\d[\d,]*(?:\.\d+)?"  # must start with a digit - a bare "," is not a number
SCALE = {"thousand": 1_000, "million": 1_000_000}

_NOUN = r"employees|people|persons|associates|colleagues"
_VERB = r"had|have|employed"

PATTERNS = [
    # "As of <date>, ... had/have/employed [approximately] N [million] ... employees/..."
    re.compile(
        rf"[Aa]s of [A-Z][a-z]+ \d{{1,2}},? \d{{4}},?[^.]{{0,80}}?(?:{_VERB})[^.]{{0,15}}?"
        rf"(?:approximately\s+)?({_NUM})\s*(million)?[^.]{{0,60}}?(?:{_NOUN})",
    ),
    # "... had/have/employed [approximately] N [million] employees ..." (no trailing
    # whitespace requirement - "employees," / "employees." must still match)
    re.compile(
        rf"(?:{_VERB})[^.]{{0,15}}?(?:approximately\s+)?({_NUM})\s*(million)?"
        rf"[^.]{{0,60}}?(?:{_NOUN})",
    ),
    # "approximately N [million] ... employees/associates/persons as of <date>"
    re.compile(
        rf"approximately\s+({_NUM})\s*(million)?\s+(?:full-time|full time|part-time)?[\w\s\-]{{0,20}}"
        rf"(?:{_NOUN})\s+as of",
        re.IGNORECASE,
    ),
]

MULTI_YEAR_PATTERN = re.compile(
    r"number of regular employees was\s+([\d,]+)\s*(thousand)?,\s*([\d,]+)\s*(thousand)?,?\s*and\s*"
    r"([\d,]+)\s*(thousand)?\s+at years ended\s+(\d{4}),\s*(\d{4}),?\s*and\s*(\d{4})",
    re.IGNORECASE,
)


@dataclass
class Candidate:
    year: int
    value: int
    quote: str


def _to_number(raw: str, scale_word: str | None) -> float:
    n = float(raw.replace(",", ""))
    if scale_word:
        n *= SCALE[scale_word.lower()]
    return n


def fetch_filing_list(cik: str, ticker: str) -> pd.DataFrame:
    """10-K filings for a company: form, filingDate, reportDate, accessionNumber, primaryDocument."""
    cik = CIK_OVERRIDES.get(ticker, cik)
    cik10 = str(cik).zfill(10)
    try:
        data = cached_json(SUBMISSIONS_URL.format(cik=cik10), "economic", f"submissions_{cik10}.json")
    except Exception as e:
        print(f"  skip {ticker} ({cik10}): {e}")
        return pd.DataFrame()
    recent = data.get("filings", {}).get("recent", {})
    if not recent:
        return pd.DataFrame()
    df = pd.DataFrame(
        {k: recent[k] for k in ["form", "filingDate", "reportDate", "accessionNumber", "primaryDocument"]}
    )
    return df[df["form"] == "10-K"].sort_values("filingDate", ascending=False).reset_index(drop=True)


def _clean_html(html: str) -> str:
    text = re.sub("<[^>]+>", " ", html)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def extract_headcount(cik: str, ticker: str, accession: str, primary_doc: str, report_date: str) -> list[Candidate]:
    """Download one 10-K (cached) and return the best total-headcount candidate(s).

    Normally returns 0 or 1 candidate (the max of everything found, after dropping
    litigation-context matches). The multi-year sentence, when present, returns up
    to 3 candidates (one per year it names) instead.
    """
    cik = CIK_OVERRIDES.get(ticker, cik)
    cik_int = int(cik)
    accn_nodash = accession.replace("-", "")
    url = ARCHIVE_URL.format(cik_int=cik_int, accn_nodash=accn_nodash, doc=primary_doc)
    filename = f"10k_{str(cik).zfill(10)}_{accn_nodash}.htm"
    try:
        path = cached_download(url, "economic", filename)
    except Exception as e:
        print(f"  skip {ticker} 10-K {accession}: {e}")
        return []
    text = _clean_html(path.read_text(encoding="utf-8", errors="ignore"))
    report_year = int(report_date[:4])

    multi = MULTI_YEAR_PATTERN.search(text)
    if multi:
        vals = [
            (_to_number(multi.group(1), multi.group(2)), int(multi.group(7))),
            (_to_number(multi.group(3), multi.group(4)), int(multi.group(8))),
            (_to_number(multi.group(5), multi.group(6)), int(multi.group(9))),
        ]
        quote = multi.group(0)
        return [Candidate(year=yr, value=int(round(val)), quote=quote) for val, yr in vals]

    best: Candidate | None = None
    for pat in PATTERNS:
        for m in pat.finditer(text):
            ctx = text[max(0, m.start() - 120) : m.end() + 30]
            if BAD_CONTEXT.search(ctx):
                continue
            value = _to_number(m.group(1), m.group(2))
            if value < 50 or value > 5_000_000:  # sanity bounds
                continue
            if best is None or value > best.value:
                best = Candidate(year=report_year, value=int(round(value)), quote=ctx.strip())

    return [best] if best else []
