"""Company audit - everything behind one company's score, for a human to check by eye.

Not a check with a verdict (leading underscore: `run.py verify` skips it) - the dashboard's
"Audit a company" exhibit calls `audit(ticker)`:

1. In its own words: the most concrete sentences of the company's latest 10-K about the planet
   (emissions, climate, EPA), its people (safety, injuries, unions, discrimination) and legal
   trouble (lawsuits, penalties, settlements) - picked by keyword and by containing a number or a
   date, hedged boilerplate ("may", "could") pushed down. From the 10-Ks already cached in
   economic/raw/ (downloaded by the headcount scripts). Exact sentences, never rewritten.
2. On the regulator's record: its federal EPA civil enforcement cases (EPA ECHO) and its
   large US facilities' greenhouse gas emissions (EPA GHGRP), with links.
3. In the news: recent headlines about the company from the GDELT 2.0 DOC API
   (https://api.gdeltproject.org/api/v2/doc/doc, free, no key, one request per 5 s),
   filtered with sustainability words (fine, lawsuit, emissions, strike, layoffs ...).
   Headline + outlet + date + link only. Cached per company per day in checks/raw/news/.
   The news is context for a human - it never changes a score.
"""

from __future__ import annotations

from pathlib import Path

import glob
import re
import time
import urllib.parse

import pandas as pd

from common.config import CATEGORIES, ROOT, UNIVERSE_CSV, catalog_path, indicator_path
from common.io import cached_json, today_utc

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"
NEWS_WORDS = ("lawsuit OR fine OR penalty OR emissions OR pollution OR spill OR strike OR layoffs "
              "OR union OR safety OR recall OR climate OR discrimination OR settlement")
SUFFIX = re.compile(r"\s*\(.*?\)|,?\s+(Inc\.?|Incorporated|Corporation|Corp\.?|Company|Co\.?|plc|Ltd\.?|N\.V\.|Holdings?|Group|& Co\.?)$", re.I)
_last_call = [0.0]


def short_name(name: str) -> str:
    prev = None
    while prev != name:
        prev, name = name, SUFFIX.sub("", name).strip()
    return name


def whole_words(text: str) -> str:
    """The stored quotes are fixed-width windows; drop the cut-off word at each end."""
    text = re.sub(r"\s+", " ", text).strip()
    if text and not text[0].isupper() and " " in text:
        text = text.split(" ", 1)[1]
    if text and text[-1] not in '.!?)"' and " " in text:
        text = text.rsplit(" ", 1)[0]
    return "…" + text.replace("�", "").strip() + "…"


THEMES = {
    "planet": r"greenhouse gas|\bGHG\b|emissions|climate|carbon|Environmental Protection Agency|\bEPA\b|pollut|hazardous (?:waste|substances)|renewable|spill|contaminat",
    "people": r"\bsafety\b|injur|\bOSHA\b|fatalit|collective bargaining|labor unions?|unionized|work stoppage|\bstrikes?\b|discriminat|harass|turnover",
    "legal": r"lawsuit|class action|litigation|consent decree|civil penalt|settlement agreement|agreed to pay|\bfined\b|violations? of|alleg",
}
CONCRETE = re.compile(r"\$\s?\d|\d[\d,.]*\s?(?:%|percent|metric tons|tons|tonnes|million|billion)|\b(?:19|20)\d\d\b")
HEDGE = re.compile(r"\b(?:may|could|might|cannot assure|no assurance|forward-looking|risk factors?)\b", re.I)
NOT_THEME = re.compile(r"tax benefit|derivative|stock awards|shares? (?:were|are) reserved|European Union", re.I)
ABBREV_END = re.compile(r"(?:\b[A-Z]|U\.S|No|Inc|Corp|Co|Mr|Ms|Dr|Jr|St|vs)\.$")


def _sentences(text: str) -> list[str]:
    parts, out = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text), []
    for part in parts:
        if out and ABBREV_END.search(out[-1]):
            out[-1] += " " + part
        else:
            out.append(part)
    return out


def latest_10k(cik10: str) -> Path | None:
    files = sorted(glob.glob(str(ROOT / "economic" / "raw" / f"10k_{cik10}_*.htm")))
    return Path(files[-1]) if files else None


def filing_passages(cik10: str, per_theme: int = 2) -> dict:
    """The company's own most concrete 10-K sentences per theme, with the filing link."""
    from social.scripts.ceo_pay_ratio import to_text

    path = latest_10k(cik10)
    if path is None:
        return {"url": None, "passages": []}
    accn = path.stem.split("_")[2]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik10)}/{accn}/"
    text = to_text(path.read_text(encoding="utf-8", errors="ignore")).replace("�", " ")
    sentences = [re.sub(r"\s+", " ", x).strip() for x in _sentences(text)]
    out = []
    for theme, pattern in THEMES.items():
        rx = re.compile(pattern, re.I)
        scored = []
        for sent in sentences:
            if not 80 <= len(sent) <= 360 or not rx.search(sent) or NOT_THEME.search(sent):
                continue
            score = 2 * bool(CONCRETE.search(sent)) + len(rx.findall(sent)) - 2 * len(HEDGE.findall(sent))
            if score >= 2:
                scored.append((score, sent))
        seen = set()
        for score, sent in sorted(scored, key=lambda x: -x[0]):
            if sent[:60] in seen:
                continue
            seen.add(sent[:60])
            out.append({"theme": theme, "text": sent, "keywords": sorted({m.group(0) for m in rx.finditer(sent)}, key=len, reverse=True)})
            if sum(1 for o in out if o["theme"] == theme) >= per_theme:
                break
    return {"url": url, "filed": accn, "passages": out}


def filing_quotes(ticker: str) -> list[dict]:
    out = []
    for category in CATEGORIES:
        catalog = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        for _, ind in catalog[catalog["status"] == "ready"].iterrows():
            path = indicator_path(category, ind["indicator_id"])
            if not path.exists():
                continue
            df = pd.read_csv(path, dtype={"note": str})
            rows = df[df["ticker"] == ticker].sort_values("year")
            if rows.empty:
                continue
            r = rows.iloc[-1]
            note = str(r.get("note") or "")
            quotes = re.findall(r'quote: "+(.{40,400}?)"+(?:\s*\||;|$)', note)
            if not quotes:
                continue
            out.append({"category": category, "indicator_id": ind["indicator_id"], "name": ind["name"], "year": int(r["year"]),
                        "value": float(r["value"]), "unit": ind["unit"], "source_url": r["source_url"],
                        "quote": whole_words(quotes[0])})
    return out


def regulator_record(ticker: str, cik: str) -> dict:
    epa_path = ROOT / "environmental" / "raw" / "epa_penalty_matches.csv"
    cases = []
    if epa_path.exists():
        m = pd.read_csv(epa_path, dtype={"cik": str})
        m = m[m["cik"].str.zfill(10) == cik].sort_values(["year", "share_usd"], ascending=[False, False])
        cases = [{"case": r["case_number"], "year": int(r["year"]), "defendant": r["name"], "penalty_usd": float(r["share_usd"]),
                  "url": f"https://echo.epa.gov/enforcement-case-report?id={r['case_number']}"} for _, r in m.iterrows()]
    ghg = None
    ghg_path = ROOT / "environmental" / "raw" / "ghg_intensity_raw_ratio.csv"
    if ghg_path.exists():
        g = pd.read_csv(ghg_path)
        g = g[(g["ticker"] == ticker) & (g["co2e_tonnes"] > 0)].sort_values("year")
        if not g.empty:
            r = g.iloc[-1]
            ghg = {"year": int(r["year"]), "tonnes": float(r["co2e_tonnes"]), "per_musd": float(r["raw_ratio"]),
                   "url": "https://ghgdata.epa.gov/ghgp/main.do"}
    return {"epa_cases": cases, "ghg": ghg}


def news(name: str, ticker: str) -> dict:
    query = f'"{short_name(name)}" ({NEWS_WORDS}) sourcelang:english'
    # a plain search link for a person to click - always shown, and the fallback when GDELT is down
    human = "https://news.google.com/search?" + urllib.parse.urlencode({"q": f'"{short_name(name)}" (lawsuit OR fine OR emissions OR strike OR layoffs)', "hl": "en-US"})
    params = {"query": query, "mode": "artlist", "format": "json", "maxrecords": "12", "sort": "datedesc", "timespan": "3months"}
    url = GDELT + "?" + urllib.parse.urlencode(params)
    wait = 5.5 - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    try:
        data = cached_json(url, "checks", f"news/{ticker}_{today_utc()}.json", pause_s=0)
    except Exception as exc:  # noqa: BLE001 - news is optional context
        from common.config import raw_dir

        (raw_dir("checks") / f"news/{ticker}_{today_utc()}.json").unlink(missing_ok=True)  # never cache a failed answer
        return {"query": query, "search_url": human, "articles": [], "error": f"live news feed unavailable right now ({exc.__class__.__name__})"}
    if not isinstance(data, dict):
        return {"query": query, "search_url": human, "articles": [], "error": "live news feed returned no data (rate limit)"}
    arts = [{"title": a.get("title", ""), "domain": a.get("domain", ""), "date": str(a.get("seendate", ""))[:8], "url": a.get("url", "")}
            for a in data.get("articles", [])]
    return {"query": query, "search_url": human, "articles": arts}


def audit(ticker: str, with_news: bool = True, only_news: bool = False) -> dict:
    universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False).set_index("ticker")
    if ticker not in universe.index:
        raise KeyError(ticker)
    row = universe.loc[ticker]
    cik = row["cik"].zfill(10)
    if only_news:  # the dashboard asks for news separately, so a slow news service never blocks the rest
        return {"ticker": ticker, "news": news(row["name"], ticker)}
    return {
        "ticker": ticker, "name": row["name"], "sector": row["sector"], "sub_industry": row.get("sub_industry", ""),
        "filings": filing_quotes(ticker),
        "tenk": filing_passages(cik),
        "regulators": regulator_record(ticker, cik),
        "news": news(row["name"], ticker) if with_news else None,
    }
