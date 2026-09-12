"""Match entity names / EINs in government datasets to S&P 500 companies.

Used by workplace_injury_rate (OSHA) and employer_retirement_contribution (Form 5500),
whose rows name the legal entity that filed, not the listed parent.

Match order, most reliable first:
  1. ein         - the filer's EIN equals the parent's EIN (SEC submissions API)
  2. name        - normalised name equals the parent's current or former SEC name
  3. subsidiary  - normalised name equals a subsidiary listed in the parent's 10-K
                   Exhibit 21 (social/raw/subsidiaries.csv). If the name shares no word
                   with the parent's name ("Mountain View Hospital" for HCA), it must also
                   - belong to a single EIN in the dataset (else several unrelated
                     entities carry that name),
                   - have the same legal form where both show one ("Jasper Holdings Ltd."
                     in Cadence's list is not the US ESOP "Jasper Holdings, Inc."),
                   - be longer than one short word ("Ryan LLC").
A name is only used if it points to exactly one company, and names made only of generic
words ("Financial Services LLC") are dropped - a missed match beats a wrong one.

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import raw_dir  # noqa: E402
from common.io import cached_download, load_universe  # noqa: E402

CATEGORY = "social"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

LEGAL_WORDS = {
    "the", "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd",
    "limited", "llc", "lc", "lp", "llp", "plc", "pc", "na", "holding", "holdings", "group",
    "de", "md", "nv", "sa", "new",
}
GENERIC_WORDS = {
    "and", "of", "services", "service", "financial", "capital", "management", "international",
    "investments", "investment", "properties", "property", "realty", "insurance", "energy",
    "solutions", "technologies", "technology", "systems", "products", "industries", "america",
    "american", "national", "global", "usa", "us", "north", "south", "east", "west", "trust",
    "funding", "partners", "ventures", "enterprises", "operations", "resources", "development",
    "one", "first", "general", "united", "health", "care", "healthcare", "medical", "bank",
    "stores", "store", "retail", "real", "estate", "power", "electric", "gas", "water", "oil",
    "data", "software", "communications", "media", "home", "homes", "brands", "foods", "food",
    "manufacturing", "distribution", "logistics", "transportation", "leasing", "finance",
    "securities", "asset", "assets", "fund", "funds", "company", "business", "commercial",
    "pharmaceuticals", "pharma", "labs", "laboratories", "sales", "supply", "equipment",
    "associates", "hospital", "hospitals", "center", "centers", "regional", "community", "clinic",
    "physicians", "surgery", "surgical", "construction", "engineering", "contractors", "mechanical",
}


def normalise(name: object) -> str:
    """'McDonald's USA, LLC' -> 'mcdonalds usa'; 'AMAZON.COM SERVICES LLC' -> 'amazon com services'"""
    s = str(name).lower().replace("&", " and ").replace("'", "").replace("’", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(w for w in s.split() if w not in LEGAL_WORDS)


LEGAL_FORMS = {"inc": "inc", "incorporated": "inc", "corp": "corp", "corporation": "corp", "co": "co",
               "company": "co", "ltd": "ltd", "limited": "ltd", "llc": "llc", "lp": "lp", "llp": "llp",
               "plc": "plc"}


def legal_form(name: object) -> frozenset[str]:
    """'Jasper Holdings Ltd.' -> {'ltd'}; 'McDonald's USA, LLC' -> {'llc'}"""
    s = re.sub(r"\bl\.?\s?l\.?\s?c\b", "llc", str(name).lower())
    return frozenset(LEGAL_FORMS[w] for w in re.sub(r"[^a-z0-9]+", " ", s).split() if w in LEGAL_FORMS)


def usable(norm: str) -> bool:
    words = norm.split()
    return len(norm) >= 4 and any(w not in GENERIC_WORDS and not w.isdigit() for w in words)


def clean_ein(value: object) -> str | None:
    digits = re.sub(r"\D", "", str(value)) if pd.notna(value) else ""
    return digits.zfill(9) if 8 <= len(digits) <= 9 and set(digits) != {"0"} else None


class CompanyMatcher:
    """Maps (ein, name) of a filing entity to a CIK of the S&P 500 universe."""

    def __init__(self) -> None:
        universe = load_universe()
        self.tickers: dict[str, list[str]] = {}
        for t, c in zip(universe["ticker"], universe["cik"]):
            self.tickers.setdefault(str(c).zfill(10), []).append(t)

        self.ein: dict[str, str] = {}
        for cik in self.tickers:
            path = cached_download(SUBMISSIONS_URL.format(cik=int(cik)), CATEGORY, f"submissions/CIK{cik}.json", pause_s=0.12)
            ein = clean_ein(json.loads(path.read_text(encoding="utf-8")).get("ein"))
            if ein:
                self.ein[ein] = cik

        names = [(normalise(n), str(c).zfill(10), "name") for n, c in zip(universe["name"], universe["cik"])]
        aliases = raw_dir(CATEGORY) / "aliases.csv"
        if aliases.exists():
            a = pd.read_csv(aliases, dtype=str)
            names += [(normalise(n), c, "name") for n, c in zip(a["name"], a["cik"])]
        # distinctive words of each parent's own names, e.g. {"kroger"} or {"berkshire", "hathaway"}
        self.parent_words: dict[str, set[str]] = {}
        for norm, cik, _ in names:
            words = {w for w in norm.split() if w not in GENERIC_WORDS and len(w) >= 3}
            self.parent_words.setdefault(cik, set()).update(words)
        subs = raw_dir(CATEGORY) / "subsidiaries.csv"
        if not subs.exists():
            raise SystemExit("social/raw/subsidiaries.csv missing - run python social/scripts/_subsidiaries.py")
        s = pd.read_csv(subs, dtype=str)
        names += [(normalise(n), c, "subsidiary") for n, c in zip(s["subsidiary"], s["cik"])]
        self.sub_forms: dict[str, set[str]] = {}
        for n in s["subsidiary"]:
            self.sub_forms.setdefault(normalise(n), set()).update(legal_form(n))

        by_name: dict[str, set[str]] = {}
        kind: dict[str, str] = {}
        for norm, cik, k in names:
            if not usable(norm):
                continue
            by_name.setdefault(norm, set()).add(cik)
            if kind.get(norm) != "name":  # a parent name beats a subsidiary name
                kind[norm] = k
        self.name = {n: next(iter(c)) for n, c in by_name.items() if len(c) == 1}
        self.name_kind = {n: kind[n] for n in self.name}
        print(f"matcher: {len(self.ein)} EINs, {len(self.name)} unambiguous names "
              f"({len(by_name) - len(self.name)} ambiguous dropped)")

    def match(self, eins: pd.Series, names: pd.Series) -> pd.DataFrame:
        """-> DataFrame(cik, match) aligned with the input; unmatched rows have cik None."""
        ein_norm = eins.map(clean_ein)
        name_norm = names.map(normalise)
        cik = ein_norm.map(self.ein)
        method = pd.Series("ein", index=eins.index).where(cik.notna())

        by_name = name_norm.map(self.name)
        kind = name_norm.map(self.name_kind)
        eins_per_name = ein_norm.groupby(name_norm).transform("nunique")
        shares_word = pd.Series(
            [bool(c) and not isinstance(c, float) and bool(set(n.split()) & self.parent_words.get(c, set()))
             for n, c in zip(name_norm, by_name)],
            index=names.index,
        )
        same_form = pd.Series(
            [not f or not self.sub_forms.get(n) or bool(f & self.sub_forms[n]) for n, f in zip(name_norm, names.map(legal_form))],
            index=names.index,
        )
        long_enough = name_norm.map(lambda n: len(n.split()) >= 2 or len(n) >= 6)
        strict_ok = (eins_per_name <= 1) & same_form & long_enough
        ok = by_name.notna() & ((kind == "name") | shares_word | strict_ok)
        fill = cik.isna() & ok
        cik = cik.where(~fill, by_name)
        method = method.where(~fill, kind)
        return pd.DataFrame({"cik": cik, "match": method})
