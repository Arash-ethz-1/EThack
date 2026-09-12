"""human_capital_disclosure - how specific a company's workforce disclosure is.

What it measures: since November 2020 Reg S-K Item 101(c)(2)(ii) forces every 10-K to
carry a "Human Capital Resources" discussion, so structural coverage is ~100% and what
differs between companies is not *whether* they write about their workforce but whether
they put numbers in it. This script locates that section in each company's most recent
10-K and counts how many of eight quantified disclosure types it actually contains
(headcount, gender/ethnic representation %, turnover/retention rate, training hours or
spend, a safety rate, a pay-equity figure, an engagement/survey score, a union coverage
%). Higher = more specific, measured, accountable disclosure; low = boilerplate. The
count is size-neutral by construction and the exact matched quotes go into `note`.

Source: SEC EDGAR 10-K primary documents (filing metadata from the cached submissions API)
Run:    python run.py build social human_capital_disclosure
        python social/scripts/human_capital_disclosure.py --download   # cache only

Output: social/indicators/human_capital_disclosure.csv
        social/raw/tenk/<TICKER>_<accession>.htm   (cache, git-ignored, ~1-2 GB)
        social/raw/human_capital_disclosure_sections.csv  (the extracted section per
                                                           company, for hand-checking)
"""

from __future__ import annotations

import html as htmllib
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import raw_dir  # noqa: E402
from common.io import cached_download, load_universe, today_utc, write_indicator  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "human_capital_disclosure"
SOURCE = "SEC EDGAR 10-K, Item 1 Human Capital Resources"

SUBMISSIONS_DIR = raw_dir(CATEGORY) / "submissions"
TENK_DIR = raw_dir(CATEGORY) / "tenk"
SECTIONS_OUT = raw_dir(CATEGORY) / "human_capital_disclosure_sections.csv"

ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}"


# --------------------------------------------------------------------------- metadata


def latest_tenk(cik: str) -> dict | None:
    """Most recent 10-K of one company from the cached submissions JSON (no network)."""
    path = SUBMISSIONS_DIR / f"CIK{cik}.json"
    if not path.exists():
        return None
    recent = json.loads(path.read_text(encoding="utf-8"))["filings"]["recent"]
    best = None
    for i, form in enumerate(recent["form"]):
        if form != "10-K":
            continue
        row = {
            "filing_date": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "document": recent["primaryDocument"][i],
            "report_date": recent["reportDate"][i],
        }
        if best is None or row["filing_date"] > best["filing_date"]:
            best = row
    if best is None or not best["document"] or not best["report_date"]:
        return None
    acc = best["accession"].replace("-", "")
    best["url"] = ARCHIVE.format(cik=int(cik), acc=acc, doc=best["document"])
    best["filename"] = f"tenk/{acc}_{best['document'].split('/')[-1]}"
    return best


def filing_index() -> list[dict]:
    """One row per ticker: the most recent 10-K we can reach. Skips CIKs without one."""
    universe = load_universe()
    rows, skipped = [], []
    for r in universe.itertuples():
        meta = latest_tenk(str(r.cik).strip())
        if meta is None:
            skipped.append(r.ticker)
            continue
        rows.append({"ticker": r.ticker, "cik": str(r.cik).strip(), **meta})
    if skipped:
        print(f"no 10-K in the cached submissions for {len(skipped)}: {', '.join(skipped)}")
    return rows


def download_all(rows: list[dict]) -> None:
    """Cache every primary document under social/raw/tenk/ (~1-2 GB, one pass)."""
    todo = [r for r in rows if not (raw_dir(CATEGORY) / r["filename"]).exists()]
    print(f"{len(rows)} filings, {len(todo)} to download")
    for i, r in enumerate(todo, 1):
        try:
            cached_download(r["url"], CATEGORY, r["filename"], pause_s=0.15)
        except Exception as exc:  # a single dead URL must not kill the run
            print(f"  FAILED {r['ticker']}: {exc}")
        if i % 25 == 0:
            print(f"  {i}/{len(todo)}")


# ---------------------------------------------------------------------------- parsing

_SCRIPT = re.compile(r"(?is)<(script|style)[^>]*>.*?</\1>")
_TAG = re.compile(r"(?s)<[^>]+>")
_BLOCK = re.compile(r"(?i)</?(p|div|tr|br|h[1-6]|table|li)\b[^>]*>")
# inline tags split words in EDGAR HTML ("approximatel<span>y</span>"), so they must go
# without leaving a space behind, unlike block tags.
_INLINE = re.compile(r"(?i)</?(span|font|b|i|u|em|strong|sup|sub|small|big|a|ix:[\w-]+)\b[^>]*>")


def to_text(raw: bytes) -> str:
    """HTML -> plain text. Block tags become newlines so headings stay on their own line."""
    text = raw.decode("utf-8", errors="replace")
    text = _SCRIPT.sub(" ", text)
    text = _INLINE.sub("", text)
    text = _BLOCK.sub("\n", text)
    text = _TAG.sub(" ", text)
    text = htmllib.unescape(text)
    text = text.replace("\xa0", " ").replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    for dash in "–—‐‑‒―":
        text = text.replace(dash, "-")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text


# Headings that open the human-capital discussion, best (most specific) first. A heading
# is a short line of its own built only of words - the digit-free wrapper is what keeps
# table-of-contents lines ("Human Capital ... 15") and sentences out.
HEADING_KEYS = [
    r"human capital\w*",
    r"(?:our|about our|focus on our|investing in our|supporting our)\s+"
    r"(?:people|employees|workforce|associates|team members|colleagues|talent|workers)",
    r"(?:people|employees|workforce|talent|culture|associates|team members)"
    r"\s*(?:,|and|&)\s*(?:culture|people|talent|community|communities|diversity|inclusion|"
    r"development|engagement|human capital|benefits|workplace)",
    r"(?:employees|people|workforce|associates|team members|colleagues|our team)",
    r"talent\s+(?:management|development|acquisition|strategy)",
    r"(?:workforce|employee|team member)\s+(?:engagement|development|experience)",
]
_WRAP = r"[A-Za-z&,'/ -]{0,30}"
HEADING_RE = [
    re.compile(r"(?im)^[\s\d.ivx()•-]{0,8}(" + _WRAP + r"\b" + k + r"\b" + _WRAP + r")[\s:.-]*$")
    for k in HEADING_KEYS
]

# Where the section stops: the next Item, Part, or the next unrelated major heading, each
# on a line of its own. "Item 1A." usually carries its title on the same line.
END_RE = re.compile(
    r"(?im)^[ ]{0,4}(?:"
    r"item\s+\d+[a-c]?\b[^\n]{0,60}"  # Item 1A. Risk Factors, Item 2. Properties, ...
    r"|part\s+[iv]+\b[^\n]{0,40}"
    r"|(?:available information|information about our executive officers|executive officers"
    r"(?: of the registrant| and other senior management)?|risk factors|our properties|"
    r"properties|legal proceedings|unresolved staff comments|government regulation|"
    r"governmental regulation|regulation(?:s)?(?: and supervision)?|supervision and"
    r" regulation|regulatory (?:matters|environment|oversight)|intellectual property|"
    r"seasonality|competition|research and development|environmental matters|"
    r"corporate (?:information|governance)|website access|available information|"
    r"forward[- ]looking statements|climate change|backlog|raw materials|suppliers|"
    r"sales and marketing|our strategy|business strategy|segment information|"
    r"where you can find (?:more|additional) information|investor information|"
    r"general development of business|reportable segments|products and services|"
    r"manufacturing|distribution|customers|insurance|patents|trademarks)"
    r")[ :.\-]*$"
)

MAX_SECTION_CHARS = 30000
MIN_SECTION_CHARS = 400
SCORE_WINDOW = 2500  # a candidate is judged on its opening, not on how far it over-runs


def find_section(text: str) -> tuple[str, str] | None:
    """Return (heading, section text) for the human-capital discussion, or None.

    Candidates are scored by how much workforce vocabulary their opening contains, so a
    table-of-contents line ("Human Capital .... 7") loses against the real section.
    Sub-headings inside the discussion ("Our Workforce", "Attracting and retaining
    employees") are candidates as well, so candidate spans that touch each other are
    merged: the section runs from the first of them to the end of the last.
    """
    found = []
    for rank, pattern in enumerate(HEADING_RE):
        for m in pattern.finditer(text):
            heading = m.group(1).strip()
            if _RISK_HEADING.search(heading):
                continue  # "Risks related to human capital" is Item 1A, not the discussion
            span = _section_at(text, m.start())
            if span is None:
                continue
            start, end = span
            score = _topic_score(text[start : start + SCORE_WINDOW]) - RANK_PENALTY * rank
            if score > 0:
                found.append({"start": start, "end": end, "heading": heading, "score": score})
    if not found:
        return None

    found.sort(key=lambda c: c["start"])
    clusters: list[list[dict]] = [[found[0]]]
    for cand in found[1:]:
        if cand["start"] <= max(c["end"] for c in clusters[-1]) + MERGE_GAP:
            clusters[-1].append(cand)
        else:
            clusters.append([cand])
    cluster = max(clusters, key=lambda cl: max(c["score"] for c in cl))
    start = cluster[0]["start"]
    end = min(max(c["end"] for c in cluster), start + MAX_SECTION_CHARS)
    return cluster[0]["heading"], text[start:end].strip()


def _section_at(text: str, heading_start: int) -> tuple[int, int] | None:
    """Span of the text under one heading, cut at the next Item / off-topic heading."""
    nl = text.find("\n", heading_start)
    body_start = nl + 1 if nl != -1 else len(text)
    end = body_start + MAX_SECTION_CHARS
    stop = END_RE.search(text, body_start, end)
    if stop:
        end = stop.start()
    body = _trim_tail(text[body_start:end].strip())
    if len(body) < MIN_SECTION_CHARS:
        return None
    return body_start, body_start + len(body)


MERGE_GAP = 1500  # a table of footnotes or a page break between two parts of one section
RANK_PENALTY = 2  # a vaguer heading ("Employees") must be much more on-topic to win


_RISK_HEADING = re.compile(r"(?i)\brisks?\b")


_HEADINGY = re.compile(r"^[A-Z0-9][^a-z\n]{2,69}$|^(?:[A-Z][\w'&/,.-]*[ ]?){1,9}$")
OFFTOPIC_WINDOW = 1500
OFFTOPIC_MAX_SCORE = 2
MIN_OFFTOPIC_CHARS = 600  # too little text left to judge - keep it rather than lose it
MAX_DIGIT_SHARE = 0.03  # a number-dense block is a workforce table, not the next section


def _trim_tail(body: str) -> str:
    """Cut the section at the first heading-like line that opens an off-topic passage.

    Many 10-Ks put no "Item" line between the human-capital discussion and what follows
    ("Government Regulation", "Our Strategy", ...), so heading names alone are not enough:
    the heading must itself be free of workforce words (otherwise "Global workforce" above
    a headcount table would cut the section in half) and the text after it must have
    stopped talking about the workforce.
    """
    pos = 0
    for line in body.split("\n"):
        stripped = line.strip()
        if (
            pos > 0
            and 2 < len(stripped) <= 70
            and not stripped.endswith((".", ",", ";", ":"))
            and _HEADINGY.match(stripped)
            and _topic_score(stripped) == 0
            and _is_offtopic(body[pos : pos + OFFTOPIC_WINDOW])
        ):
            return body[:pos].strip()
        pos += len(line) + 1
    return body


def _is_offtopic(window: str) -> bool:
    """True if what follows a heading has stopped being about the workforce."""
    if len(window) < MIN_OFFTOPIC_CHARS:
        return False
    if sum(c.isdigit() for c in window) / len(window) > MAX_DIGIT_SHARE:
        return False  # a headcount / diversity / turnover table, still the same section
    return _topic_score(window) <= OFFTOPIC_MAX_SCORE


_TOPIC_WORDS = re.compile(
    r"(?i)\b(employee|employees|workforce|workers|associates|team members|colleagues|"
    r"talent|hiring|hire\w*|recruit\w*|retention|turnover|training|benefits|compensation|"
    r"diversity|inclusion|safety|engagement|wellbeing|well-being|wellness|labor|union|"
    r"collective bargaining|development|culture|our people|workplace|wages|career|careers|"
    r"mentoring|leadership|employment|staff|personnel)\b"
)


def _topic_score(body: str) -> int:
    """How much of this text is really about the workforce (distinct vocabulary used)."""
    return len({m.group(0).lower() for m in _TOPIC_WORDS.finditer(body)})


# ------------------------------------------------------------------------- detection

NUM = r"(?:\d[\d,]*(?:\.\d+)?)"
PCT = r"(?:\d{1,3}(?:\.\d+)?\s?(?:%|percent))"
WORKER = (
    r"(?:employees|team members|teammates|associates|colleagues|co[- ]?workers|workers|"
    r"crew members|cast members|persons|people|individuals|staff members|staff|personnel|"
    r"(?:employee )?equivalents?|FTEs?|professionals)\b"
)
# tables put the label and the number on different lines, so a few line breaks are allowed
GAPN = r"(?:[^.\n]{0,90}\n?){0,3}"
RATE = r"(?:\d{1,3}\.\d+)"  # a safety rate is always a decimal (0.41, 2.34)

# Each type: a list of regexes. A hit must contain a number - that is the whole point of
# the indicator. The matched text (trimmed to a readable window) goes into `note`.
DISCLOSURE_TYPES: dict[str, list[str]] = {
    # Total headcount. Anchored on a reporting verb ("we employed 118,000 persons") or on
    # a workforce noun, so "300,000 employees took a course" is not read as headcount.
    "headcount": [
        rf"\b(?:had|have|has|employ|employs|employed|employing|totaled|totaling|numbered|"
        rf"with|our)\s+(?:approximately|about|roughly|over|more than|nearly|some|"
        rf"in excess of|a total of|almost)?\s*{NUM}\s*(?:million|thousand)?\s*"
        rf"(?:[\w][\w,.-]*\s+){{0,5}}{WORKER}",
        rf"(?:workforce|headcount|head count|employee (?:base|population|count)|"
        rf"number of (?:our |full[- ]time |part[- ]time |global )*(?:employees|associates|"
        rf"team members|teammates|colleagues|workers)|global team|total (?:employees|"
        rf"associates|team members|teammates|headcount))"
        rf"{GAPN}(?:was|of|is|are|totaled|comprised|consisted of|consists of|stood at|"
        rf"includes?|included|increased to|decreased to|to|:)\s*"
        rf"(?:approximately|about|over|more than|nearly|roughly)?\s*{NUM}",
        rf"as of [^.\n]{{0,45}}(?:approximately|about|roughly|over|more than|nearly)?\s*"
        rf"{NUM}\s*(?:[\w][\w,.-]*\s+){{0,4}}{WORKER}",
        rf"{WORKER}[^.\n]{{0,160}}(?:totaled|totalled|numbered|stood at)\s*"
        rf"(?:approximately|about|roughly|over|more than|nearly)?\s*{NUM}",
        # company-specific words for staff ("AutoZoners", "crew members") - the verb is
        # what makes this a headcount, so no noun is required after the number
        rf"\b(?:employed|employs|employ)\s+(?:approximately|about|roughly|over|"
        rf"more than|nearly|some|a total of|almost|in excess of)?\s*{NUM}\b",
        rf"{NUM}\s*(?:[\w][\w,.-]*\s+){{0,3}}{WORKER}[^.\n]{{0,40}}"
        rf"(?:are|were|is|was)\s+employed\b",
        # a headcount table: "Full-Time Associates 33,755 1,426 35,181"
        rf"^(?:full|part)[- ]time[^\n]{{0,30}}\s[\d,]{{4,}}",
    ],
    # Gender / ethnic representation as a percentage of the workforce.
    "representation_pct": [
        # a table: a short line naming a gender/ethnicity column, a percentage just below
        rf"^[^.\n]{{0,60}}\b(?:women|female|gender|ethnicity|race|minorit\w*|"
        rf"people of color|underrepresented)\b[^.\n]{{0,60}}$"
        rf"(?:\n[^\n]{{0,140}}){{0,4}}\n[^\n]{{0,140}}{PCT}",
        rf"{PCT}{GAPN}\b(?:women|woman|female|gender|racially|ethnic\w*|"
        rf"minorit\w*|people of color|underrepresented|black|hispanic|latin[oax]\w*|asian|"
        rf"indigenous)\b",
        rf"\b(?:women|female|gender|racially|ethnic\w*|minorit\w*|people of color|"
        rf"underrepresented|black|hispanic|latin[oax]\w*|asian|indigenous)\b{GAPN}{PCT}",
    ],
    # Voluntary turnover / attrition / retention rate.
    "turnover_retention": [
        rf"\b(?:voluntary|involuntary|overall|total|annual\w*|global|employee|regretted)?\s*"
        rf"(?:turnover|attrition|retention)\s*(?:rate|ratio|level)?[^.\n]{{0,60}}{PCT}",
        rf"{PCT}[^.\n]{{0,60}}\b(?:voluntary |involuntary |overall |annual |employee )?"
        rf"(?:turnover|attrition|retention)\b",
        rf"(?:voluntary|involuntary)\s+(?:termination|separation|departure)s?"
        rf"[^.\n]{{0,40}}{PCT}",
    ],
    # Training hours or training spend.
    "training": [
        rf"{NUM}\s*(?:million|thousand)?\s*(?:hours|hrs)\b[^.\n]{{0,80}}"
        rf"\b(?:training|learning|develop\w*|instruction|courses?|education)\b",
        rf"{NUM}\s*(?:million|thousand)?\s*(?:[\w][\w,.-]*\s+){{0,5}}"
        rf"(?:training|learning|development|instruction\w*|educational?)\s*(?:hours|hrs)\b",
        rf"\b(?:training|learning|develop\w*|upskilling|reskilling|education|tuition|"
        rf"courses?)\b[^.\n]{{0,80}}{NUM}\s*(?:million|thousand)?\s*(?:hours|hrs)\b",
        rf"(?:invested|spent|contributed|provided|reimbursed|committed)\s*"
        rf"(?:approximately|about|over|more than|nearly)?\s*\$\s?{NUM}\s*"
        rf"(?:million|billion|thousand)?[^.\n]{{0,80}}"
        rf"\b(?:training|learning|education|tuition|upskilling|reskilling|"
        rf"develop\w* program\w*)\b",
        rf"\b(?:training|learning|education|tuition|upskilling|reskilling)\b"
        rf"[^.\n]{{0,80}}\$\s?{NUM}\s*(?:million|billion|thousand)?",
    ],
    # A safety rate (OSHA recordable, lost-time, DART, TRIR).
    "safety": [
        rf"(?:total\s+)?(?:recordable|lost[- ]time|lost workday|days away|incident|injur\w*|"
        rf"illness|accident|fatality|DART|TRIR|TCIR|OSHA)\s*"
        rf"(?:and illness\s*|injury\s*|incident\s*|case\s*|severity\s*){{0,2}}"
        rf"(?:rate|frequency|ratio|index)[^.\n]{{0,60}}{RATE}",
        rf"{RATE}[^.\n]{{0,60}}(?:recordable|lost[- ]time|lost workday|injur\w*|incident|"
        rf"DART|TRIR)\s*(?:injury\s*|incident\s*|case\s*){{0,2}}(?:rate|frequency|index)",
    ],
    # A pay-equity / pay-gap figure.
    "pay_equity": [
        rf"(?:pay|compensation|wage|salary|gender|ethnicity)\s*(?:equity|gap|parity|"
        rf"equality|differenc\w*)[^.\n]{{0,80}}"
        rf"(?:{PCT}|{NUM}\s*(?:to|:)\s*{NUM}|\$\s?1(?:\.00)?\b)",
        rf"(?:{PCT}|\$\s?1(?:\.00)?)[^.\n]{{0,80}}(?:pay|compensation|wage)\s*"
        rf"(?:equity|gap|parity|equality)",
        rf"(?:women|female|minorit\w*|people of color|underrepresented)[^.\n]{{0,50}}"
        rf"\bearn\w*[^.\n]{{0,50}}(?:{PCT}|\$\s?{NUM})",
    ],
    # An engagement / survey score.
    "engagement_score": [
        rf"(?:engagement|engaged|satisfaction|favorabilit\w*|eNPS|net promoter|"
        rf"(?:employee experience|inclusion|engagement|culture) index|pulse)\s*(?:survey\s*|index\s*|score\s*|rate\s*|result\w*\s*|ratin\w*\s*)"
        rf"{{0,2}}[^.\n]{{0,70}}(?:{PCT}|score of\s*{NUM}|{NUM}\s*out of\s*{NUM})",
        rf"(?:{PCT}|score of\s*{NUM})[^.\n]{{0,70}}(?:engagement|favorab\w*|"
        rf"(?:employee |job )?satisfaction)",
        rf"{PCT}\s*of\s*(?:our\s*|surveyed\s*)?{WORKER}[^.\n]{{0,60}}"
        rf"(?:responded|agreed|said|reported|feel|felt|indicated|participated in (?:the |our )?"
        rf"(?:survey|engagement))",
        rf"{PCT}[^.\n]{{0,50}}(?:response rate|participation|completion rate)"
        rf"[^.\n]{{0,60}}survey",
        rf"survey[^.\n]{{0,60}}(?:response|participation) rate[^.\n]{{0,30}}{PCT}",
    ],
    # Union / collective-bargaining coverage: a percentage, or a count of covered staff.
    "union_coverage": [
        rf"{PCT}[^.\n]{{0,90}}(?:union|collective(?:ly)? bargain\w*|collective labor|"
        rf"labor agreement|works council|organized labor|CBAs?\b)",
        rf"(?:union|collective(?:ly)? bargain\w*|collective labor|labor agreement|"
        rf"works council|organized labor|CBAs?\b)[^.\n]{{0,90}}{PCT}",
        rf"{NUM}\s*(?:[A-Za-z][A-Za-z-]*\s+){{0,4}}{WORKER}[^.\n]{{0,60}}"
        rf"(?:were |are |was |is )?(?:covered by|represented by|subject to|members of|"
        rf"belong to)[^.\n]{{0,50}}(?:collective bargaining|labor union|unions?|"
        rf"works council)",
    ],
}
COMPILED = {k: [re.compile(p, re.I | re.M) for p in v] for k, v in DISCLOSURE_TYPES.items()}

# Guards: a number that is a year, a dollar amount of revenue, a footnote marker etc.
_YEAR_ONLY = re.compile(r"^(?:19|20)\d\d$")


def detect(section: str) -> dict[str, str]:
    """Quantified disclosure types present in the section -> the verbatim matched quote."""
    hits: dict[str, str] = {}
    for name, patterns in COMPILED.items():
        for pattern in patterns:
            for m in pattern.finditer(section):
                quote = _quote(section, m.start(), m.end())
                if _plausible(name, m.group(0)):
                    hits[name] = quote
                    break
            if name in hits:
                break
    return hits


# Phrases that make a match about something other than the workforce.
_WRONG_SUBJECT = re.compile(
    r"(?i)\b(?:customer|client|subscriber|revenue|net|gross|dollar|member|user|patient|"
    r"guest|policy|sales) (?:retention|turnover|satisfaction)\b"
)


def _plausible(name: str, matched: str) -> bool:
    """Reject matches whose number is only a year, or that are about customers, not staff."""
    numbers = re.findall(r"\d[\d,]*(?:\.\d+)?", matched)
    numbers = [n for n in numbers if not _YEAR_ONLY.match(n.replace(",", ""))]
    if not numbers:
        return False
    if _WRONG_SUBJECT.search(matched):
        return False
    if name == "training" and re.search(r"(?i)volunteer", matched):
        return False
    if name == "headcount":
        # a headcount below 50 is almost always something else (board members, sites)
        biggest = max(float(n.replace(",", "")) for n in numbers)
        if biggest < 50 and not re.search(r"(?i)\b(?:million|thousand)\b", matched):
            return False
    return True


def _quote(section: str, start: int, end: int, pad: int = 60) -> str:
    """The matched text plus a little context, cut at sentence-ish boundaries."""
    left = section.rfind(".", max(0, start - pad), start)
    left = left + 1 if left != -1 else max(0, start - pad)
    right = section.find(".", end, end + pad)
    right = right + 1 if right != -1 else min(len(section), end + pad)
    return " ".join(section[left:right].split()).strip()


# ----------------------------------------------------------------------------- build


def build() -> pd.DataFrame:
    rows_meta = filing_index()
    download_all(rows_meta)

    rows, sections, no_section, no_file = [], [], [], []
    for meta in rows_meta:
        path = raw_dir(CATEGORY) / meta["filename"]
        if not path.exists():
            no_file.append(meta["ticker"])
            continue
        found = find_section(to_text(path.read_bytes()))
        if found is None:
            no_section.append(meta["ticker"])
            continue
        heading, section = found
        hits = detect(section)
        note = f'heading "{heading}"; ' + (
            " | ".join(f'{k}: "{v}"' for k, v in sorted(hits.items()))
            if hits
            else "no quantified disclosure type matched"
        )
        rows.append(
            {
                "ticker": meta["ticker"],
                "year": int(meta["report_date"][:4]),
                "value": len(hits),
                "source": SOURCE,
                "source_url": meta["url"],
                "retrieved": today_utc(),
                "note": note[:1500],
            }
        )
        sections.append(
            {
                "ticker": meta["ticker"],
                "heading": heading,
                "types": ";".join(sorted(hits)),
                "n_types": len(hits),
                "chars": len(section),
                "url": meta["url"],
                "section": section,
            }
        )

    if no_file:
        print(f"no cached document for {len(no_file)}: {', '.join(no_file)}")
    if no_section:
        print(f"no human-capital section found for {len(no_section)}: {', '.join(no_section)}")
    pd.DataFrame(sections).to_csv(SECTIONS_OUT, index=False, lineterminator="\n")
    print(f"wrote {SECTIONS_OUT.name}: {len(sections)} extracted sections (for hand-checks)")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    if "--download" in sys.argv:
        download_all(filing_index())
    else:
        write_indicator(CATEGORY, INDICATOR_ID, build())
