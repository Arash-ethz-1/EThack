"""Shared helper: which materials each S&P 500 company names in its own 10-K.

EDGAR full-text search indexes every filing document from 2001 on. Searching it per
material per year gives, for each company, the list of critical materials it tells
its own investors it depends on - with the accession number of the filing that says
so, which is the citation.

This is company evidence, not an industry average: two semiconductor companies can
name different materials, and the same company names different materials in
different years.

    https://efts.sec.gov/LATEST/search-index?q="rare earth"&forms=10-K

Only hits for S&P 500 filers are cached, so the cache stays small; the query that
produced them is recorded next to each file in raw/_downloads.csv.

Not an indicator - the leading underscore keeps `python run.py build` from running it.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from common.config import raw_dir
from common.io import http_headers

CATEGORY = "environmental"
FTS_URL = "https://efts.sec.gov/LATEST/search-index"
FTS_CITE = "https://efts.sec.gov/LATEST/search-index?q={term}&forms=10-K"

PAGE = 100
MAX_HITS = 10_000  # EDGAR refuses to page deeper than this
PAUSE_S = 0.25  # SEC asks for <= 10 requests/second; stay well under

# Search term -> the USGS commodity it stands for. Deliberately excludes words that
# are common in a non-material sense in filings (gold, silver, tin, steel, lead),
# because a hit on those says more about the English language than about supply risk.
TERM_TO_MATERIAL = {
    '"rare earth"': "Rare Earths",
    "cobalt": "Cobalt",
    "lithium": "Lithium",
    "titanium": "Titanium Sponge Metal",
    "palladium": "Palladium",
    "platinum": "Platinum",
    "copper": "Copper",
    "nickel": "Nickel",
    "aluminum": "Aluminum",
    "tungsten": "Tungsten",
    "gallium": "Gallium",
    "graphite": "Graphite (Natural)",
    "tantalum": "Tantalum",
    "helium": "Helium",
    "silicon": "Silicon",
    "manganese": "Manganese",
    "molybdenum": "Molybdenum",
    "niobium": "Niobium (Columbium)",
    "antimony": "Antimony",
    "magnesium": "Magnesium Metal",
    "zirconium": "Zirconium",
    "beryllium": "Beryllium",
    "indium": "Indium",
    "tellurium": "Tellurium",
}


def filing_url(cik: str, adsh: str) -> str:
    """The EDGAR index page for one filing - the citation behind every row."""
    return (
        f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
        f"{adsh.replace('-', '')}/{adsh}-index.htm"
    )


def _cache_path(term: str, year: int) -> Path:
    slug = term.strip('"').replace(" ", "_")
    return raw_dir(CATEGORY) / "edgar" / f"{slug}_{year}.json"


def _fetch_page(term: str, year: int, start: int) -> dict:
    """One page of results, retrying the throttling 500s EDGAR returns under load."""
    params = {
        "q": term,
        "forms": "10-K",
        "startdt": f"{year}-01-01",
        "enddt": f"{year}-12-31",
        "from": start,
    }
    delay = 1.0
    for attempt in range(6):
        resp = requests.get(FTS_URL, params=params, headers=http_headers(), timeout=90)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503):
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
    raise RuntimeError(f"EDGAR kept failing for {term} {year} at offset {start}")


def filings_naming(term: str, year: int, sp500_ciks: set[str], refresh: bool = False) -> list[dict]:
    """S&P 500 10-K filings filed in `year` whose text contains `term`."""
    path = _cache_path(term, year)
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))

    kept: list[dict] = []
    start, total = 0, None
    while True:
        page = _fetch_page(term, year, start)
        hits = page["hits"]["hits"]
        if total is None:
            total = page["hits"]["total"]["value"]
        for hit in hits:
            src = hit["_source"]
            for cik in src["ciks"]:
                if cik.zfill(10) in sp500_ciks:
                    kept.append(
                        {
                            "cik": cik.zfill(10),
                            "adsh": src.get("adsh", ""),
                            "period_ending": src.get("period_ending") or "",
                            "file_date": src.get("file_date") or "",
                        }
                    )
        start += len(hits)
        if not hits or start >= min(total, MAX_HITS):
            break
        time.sleep(PAUSE_S)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(kept, indent=0), encoding="utf-8")
    _log_download(path, term, year, total, len(kept))
    time.sleep(PAUSE_S)
    return kept


def _log_download(path: Path, term: str, year: int, total: int | None, kept: int) -> None:
    import csv
    import datetime as dt

    log = raw_dir(CATEGORY) / "_downloads.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["file", "url", "retrieved_utc", "bytes"])
        url = f"{FTS_URL}?q={term}&forms=10-K&startdt={year}-01-01&enddt={year}-12-31"
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        w.writerow([f"edgar/{path.name} ({total} hits, {kept} in S&P 500)", url, stamp, path.stat().st_size])


def mentions(years: list[int], sp500_ciks: set[str], refresh: bool = False) -> list[dict]:
    """One record per (company, year, material) the company named in a 10-K."""
    out = []
    for year in years:
        for term, material in TERM_TO_MATERIAL.items():
            hits = filings_naming(term, year, sp500_ciks, refresh=refresh)
            for hit in hits:
                period = hit["period_ending"][:4]
                if not period.isdigit():
                    continue
                out.append(
                    {
                        "cik": hit["cik"],
                        "year": int(period),
                        "material": material,
                        "term": term,
                        "adsh": hit["adsh"],
                    }
                )
        print(f"  {year}: {sum(1 for r in out if r['year'] == year)} company-material mentions so far")
    return out
