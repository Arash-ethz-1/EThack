"""Download federal court dockets per company from CourtListener into social/raw/.

Feeds the `labor_litigation_intensity` indicator. Separated from it so the slow download
happens once and the indicator can be recomputed instantly from the cache.

Source: https://www.courtlistener.com/api/rest/v4/search/  (free; a token raises the quota)
Run:    python social/scripts/_dockets.py [--limit N] [--universe path.csv]

Set COURTLISTENER_TOKEN in .env to avoid throttling (free: courtlistener.com/help/api/rest/).

Output: social/raw/dockets/<TICKER>.json - every docket with dateFiled + suitNature.
Leading underscore: `python run.py build social` skips it.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import raw_dir  # noqa: E402
from common.io import http_headers  # noqa: E402

CATEGORY = "social"
API = "https://www.courtlistener.com/api/rest/v4/search/"
OUT_DIR = raw_dir(CATEGORY) / "dockets"

WINDOW_FROM, WINDOW_TO = "2016-01-01", "2026-01-01"

# Federal Nature-of-Suit codes that mean "an employee sued this company over how it
# treated them". Verified against live values, which appear both with and without the
# leading code (e.g. "442 Civil Rights: Jobs" and "Civil Rights: Jobs").
NOS_CODES = {
    "442": "Civil Rights: Jobs",
    "445": "Amer w/Disabilities - Employment",
    "710": "Fair Labor Standards Act",
    "720": "Labor/Mgmt. Relations",
    "740": "Railway Labor Act",
    "751": "Family and Medical Leave Act",
    "790": "Other Labor Litigation",
    "791": "Employee Retirement Income Security Act",
}
# Broad server-side filter; the precise code filter is applied locally afterwards.
NOS_QUERY = 'suitNature:(Labor OR "Civil Rights: Jobs" OR "Fair Labor" OR Disabilities OR E.R.I.S.A.)'

CODE_RE = re.compile(r"\b(\d{3})\b")
TEXT_RE = re.compile(
    r"civil rights:?\s*jobs|fair labor|labor\s*[:/]|labor/mgt|e\.?r\.?i\.?s\.?a|"
    r"disabilit(y|ies)\s*-?\s*employ|family and medical",
    re.I,
)


def is_labor(suit_nature: str | None) -> bool:
    """True if the Nature-of-Suit is an employment/labor matter.

    Matches on the code when present (the reliable signal), otherwise on the text.
    Bankruptcy codes 422/423 start with the same digit as 442 - hence exact codes only.
    """
    if not suit_nature:
        return False
    codes = CODE_RE.findall(suit_nature)
    if codes:
        return any(c in NOS_CODES for c in codes)
    return bool(TEXT_RE.search(suit_nature))


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(http_headers())
    token = os.getenv("COURTLISTENER_TOKEN", "").strip()
    if token:
        s.headers["Authorization"] = f"Token {token}"
        print("using COURTLISTENER_TOKEN")
    else:
        print("WARN no COURTLISTENER_TOKEN in .env - anonymous quota throttles after ~10 queries")
    return s


# Corporate suffixes. `party:("3M CO")` is a PHRASE match needing the tokens 3m+co
# adjacent, but courts write "3M Company" - so the SEC name finds nothing while the
# stripped name "3M" finds 54 dockets. Measured, not assumed.
SUFFIX = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd",
    "limited", "plc", "lp", "llp", "llc", "nv", "sa", "ag", "holding", "holdings",
    "group", "the", "new", "de", "md", "cl", "class", "a", "b",
}
# Words that may follow a company name on a legitimately related party, e.g.
# "3M Pension Plan" is 3M, but "3M Contracting, LLC" is an unrelated firm.
RELATED = SUFFIX | {
    "plan", "plans", "pension", "retirement", "savings", "benefit", "benefits", "welfare",
    "committee", "board", "trust", "administrative", "usa", "us", "america", "american",
    "international", "intl", "services", "service", "systems", "technologies", "bank",
    "na", "financial", "stores", "employees", "employee", "health", "insurance",
}


def core(name: str) -> str:
    """'SMITH A O CORP' -> 'smith a o'; '3M Co' -> '3m'. Punctuation and suffixes dropped."""
    n = re.sub(r"\([^)]*\)", " ", name.lower())
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    parts = re.sub(r"\s+", " ", n).strip().split()
    while len(parts) > 1 and parts[-1] in SUFFIX:
        parts.pop()
    return " ".join(parts)


def names_for(ticker: str, display: str, aliases: list[dict]) -> list[str]:
    """Search terms: display name, SEC current name, in-window former names, all stripped.

    The display name matters on its own: 'A. O. Smith' finds 2 dockets while the SEC
    name 'SMITH A O CORP' finds 0.
    """
    raw = [display]
    for r in aliases:
        if r["ticker"] != ticker:
            continue
        if r["kind"] == "current" or (r["valid_to"] or "") >= WINDOW_FROM:
            raw.append(r["name"])

    seen, keep = set(), []
    for n in raw:
        c = core(n)
        if len(c) < 2:
            continue
        if c not in seen:
            seen.add(c)
            keep.append(c)
    return keep[:5]


# Benefit-plan words: "3M Pension Plan" really is 3M being sued over how it treats staff.
PLAN = {
    "plan", "plans", "pension", "retirement", "savings", "benefit", "benefits", "welfare",
    "disability", "committee", "board", "trust", "administrative", "leave", "center",
    "program", "programs", "fund", "health", "employee", "employees", "care",
}


def is_ambiguous(name_core: str) -> bool:
    """Short acronyms match unrelated firms: 'aes' hit 'AES Services, LLC'. Be strict.

    Only very short cores qualify - 'aflac' and 'adobe' are distinctive enough to trust.
    """
    return len(name_core) <= 4


def party_matches(parties: list[str] | None, cores: list[str]) -> bool:
    """Keep a docket only if some party really is this company.

    Two strictness tiers, because a distinctive name like 'abbott laboratories' can safely
    absorb trailing words, while the acronym 'aes' cannot:
      - ambiguous core -> only corporate suffixes and benefit-plan words may follow
        ('AES Corporation' yes, 'AES Services, LLC' no)
      - distinctive core -> the wider RELATED set may follow
    """
    for p in parties or []:
        pc = core(p)
        for c in cores:
            if pc == c:
                return True
            if pc.startswith(c + " "):
                rest = pc[len(c) + 1 :].split()
                if not rest:
                    continue
                if not is_ambiguous(c):
                    # A distinctive name followed by anything is that company:
                    # "Abbott Laboratories Group Health Care Plan", "Accenture Federal Services".
                    return True
                if all(w in SUFFIX | PLAN for w in rest):
                    return True
    return False


def fetch(sess: requests.Session, ticker: str, names: list[str]) -> dict:
    party = " OR ".join(f'"{n}"' for n in names)
    params = {
        "q": f"party:({party}) AND {NOS_QUERY}",
        "type": "r",
        "filed_after": WINDOW_FROM,
        "filed_before": WINDOW_TO,
    }
    dockets, url, pages = [], API, 0
    while url and pages < 25:  # 25 pages x 20 = 500 dockets is plenty per company
        r = sess.get(url, params=params if pages == 0 else None, timeout=60)
        if r.status_code == 429:
            raise RuntimeError("429 rate limited - set COURTLISTENER_TOKEN in .env")
        r.raise_for_status()
        d = r.json()
        for x in d.get("results", []):
            dockets.append(
                {
                    "docket_id": x.get("docket_id"),
                    "caseName": x.get("caseName"),
                    "dateFiled": x.get("dateFiled"),
                    "suitNature": x.get("suitNature"),
                    "court": x.get("court_id"),
                    "party": x.get("party"),
                }
            )
        url, pages = d.get("next"), pages + 1
        time.sleep(1.5)
    return {"ticker": ticker, "names": names, "query": params["q"],
            "total_reported": d.get("count"), "dockets": dockets}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only the first N companies (pilot)")
    ap.add_argument("--universe", type=Path, default=None)
    args = ap.parse_args()

    from common.config import UNIVERSE_CSV
    src = UNIVERSE_CSV if UNIVERSE_CSV.exists() else args.universe
    if not src or not Path(src).exists():
        raise SystemExit("no universe/sp500.csv and no --universe fallback")
    companies = list(csv.DictReader(open(src, encoding="utf-8")))
    aliases = list(csv.DictReader(open(raw_dir(CATEGORY) / "aliases.csv", encoding="utf-8")))
    if args.limit:
        companies = companies[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sess, done, labor_total = session(), 0, 0
    for row in companies:
        t = row["ticker"].strip().upper()
        path = OUT_DIR / f"{t}.json"
        if path.exists():
            continue
        names = names_for(t, row["name"], aliases)
        if not names:
            continue
        data = fetch(sess, t, names)
        # Store EVERYTHING. Party and Nature-of-Suit filtering happen in the indicator
        # script, so the matcher can be tuned without re-downloading (quota is scarce).
        path.write_text(json.dumps(data), encoding="utf-8")
        kept = [d for d in data["dockets"] if party_matches(d.get("party"), names)]
        lab = sum(1 for d in kept if is_labor(d["suitNature"]))
        labor_total += lab
        done += 1
        print(f"  {t:6} {len(data['dockets']):4} raw, {len(kept):4} this company, {lab:4} labor"
              f"   [{', '.join(names[:2])}]")
    print(f"\nfetched {done} companies, {labor_total} labor dockets total -> "
          f"{OUT_DIR.relative_to(raw_dir(CATEGORY).parent.parent).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
