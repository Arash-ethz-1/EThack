"""ceo_pay_ratio - CEO total compensation as a multiple of the median employee's.

What it measures: how the rewards of the company are shared between the top and the
typical worker. Since 2018 SEC Regulation S-K Item 402(u) requires every US-listed
company to state this ratio in its annual proxy statement (DEF 14A), computed with the
same "total compensation" definition for both. Lower is better. It is a ratio, so company
size does not matter.

How: latest DEF 14A per company from EDGAR -> HTML to text -> find "<number> to 1" /
"<number>:1" / "<number> times" with "median" in the preceding sentence(s). The exact
quote is stored in `note` so every value can be checked by hand; if a proxy states more
than one candidate number, the others are listed in `note` too.

Year: the fiscal year the proxy reports on = the last fiscal year end (SEC submissions
`fiscalYearEnd`) before the filing date. NVIDIA's "Fiscal 2026" ends Jan 2026 -> 2026.

Source: SEC EDGAR DEF 14A, https://www.sec.gov/cgi-bin/browse-edgar?type=DEF+14A
Run:    python run.py build social ceo_pay_ratio   (~500 downloads, cached in
        social/raw/proxies/, git-ignored because they total ~1 GB)

Output: social/indicators/ceo_pay_ratio.csv
Owner:  Arash
"""

from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.io import cached_download, load_universe, today_utc, write_indicator  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "ceo_pay_ratio"
SOURCE = "SEC EDGAR DEF 14A"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"

NUM = r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)"
SEP = r"\s*(-?\s*to\s*-?|:|-)\s*"
END = r"(?![\d,]*\d|\.\d)"
# (pattern, which group holds the CEO multiple)
PATTERNS = [
    (re.compile(NUM + SEP + r"(?:1|one)" + END, re.I), "forward"),            # 533 to 1, 533:1, 533-to-1, 296-1
    (re.compile(r"(?<![\d.,])(?:1|one)" + SEP + NUM + END, re.I), "reverse"),  # 1 to 346, 1-to-51, 1:178 (median : CEO)
    (re.compile(NUM + r"\s*(?:x|times)\b", re.I), "times"),                   # 533 times, 533x
]
BEFORE = 350  # characters before the number that must mention "median" or "pay ratio"


def to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    for ch in ("\xa0", "\u2009", "\u202f", "\u200b"):  # nbsp, thin spaces, zero-width space
        text = text.replace(ch, " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2019", "'")
    return re.sub(r"\s+", " ", text)


def candidates(text: str) -> list[tuple[int, float, str]]:
    """(score, value, quote) for every number that reads like the CEO pay ratio."""
    out = []
    for pat, kind in PATTERNS:
        for m in pat.finditer(text):
            before = text[max(0, m.start() - BEFORE):m.start()].lower()
            near = before[-150:]
            if "median" not in before and "pay ratio" not in before:
                continue
            number = m.group(2) if kind == "reverse" else m.group(1)
            bare_hyphen = kind == "forward" and m.group(2).strip() == "-"
            if (kind == "reverse" or bare_hyphen) and "ratio" not in near:
                continue  # "1 to 5 years" / "Proposal 3-1" only count right after the word "ratio"
            if re.fullmatch(r"(19|20)\d\d", number):
                continue  # a year, "2025: 1 ..."
            value = float(number.replace(",", ""))
            if kind == "reverse" and 0 < value < 1:
                value = round(1 / value, 2)  # "CEO to median: 1 to 0.97" -> CEO earns 1.03x
            if not 1 <= value <= 20000:
                continue
            after = text[m.end():m.end() + 120].lower()
            if kind == "times" and ("median" not in after or re.search(r"lower|higher|less|more|base|salary", after[:15])):
                continue  # "206 times that of our median employee" yes; "6x annual base pay", "3x lower than" no
            if re.search(r"s&p|peer|average|companies", near[-80:]):
                continue  # a benchmark: "the median ratio for S&P 500 companies (195:1)"
            score = (2 * ("ratio" in near) + ("ceo" in before or "chief executive" in before)
                     + 2 * (kind != "times") - ("adjusted" in near))  # PPP/"adjusted" ratios are supplementary
            quote = text[max(0, m.start() - 220):m.end() + 40].strip()
            out.append((score, value, quote))
    return out


def fiscal_year(filing_date: str, fiscal_year_end: str | None) -> int:
    filed = dt.date.fromisoformat(filing_date)
    if not fiscal_year_end or len(fiscal_year_end) != 4:
        return filed.year - 1
    month, day = int(fiscal_year_end[:2]), min(int(fiscal_year_end[2:]), 28)
    end = dt.date(filed.year, month, day)
    return end.year if end < filed else end.year - 1


def build() -> pd.DataFrame:
    universe = load_universe()
    by_cik: dict[int, list[str]] = {}
    for t, c in zip(universe["ticker"], universe["cik"]):
        by_cik.setdefault(int(c), []).append(t)

    rows, no_proxy, no_ratio = [], [], []
    for n, (cik, tickers) in enumerate(by_cik.items(), 1):
        label = "/".join(tickers)
        sub = json.loads(cached_download(SUBMISSIONS_URL.format(cik=cik), CATEGORY,
                                         f"submissions/CIK{cik:010d}.json", pause_s=0.12).read_text(encoding="utf-8"))
        rec = sub["filings"]["recent"]
        idx = next((i for i, f in enumerate(rec["form"]) if f == "DEF 14A"), None)
        if idx is None:
            no_proxy.append(label)
            continue
        acc, doc, filed = rec["accessionNumber"][idx], rec["primaryDocument"][idx], rec["filingDate"][idx]
        url = ARCHIVE_URL.format(cik=cik, acc=acc.replace("-", ""), name=doc)
        try:
            path = cached_download(url, CATEGORY, f"proxies/{tickers[0]}_{acc}_{doc}", pause_s=0.12)
        except Exception as exc:  # noqa: BLE001 - one bad filing must not kill the run
            no_proxy.append(f"{label} ({exc.__class__.__name__})")
            continue
        found = candidates(to_text(path.read_text(encoding="utf-8", errors="ignore")))
        if not found:
            no_ratio.append(label)
            continue
        # highest score; ties go to the number the proxy repeats most, then to the first one
        repeats = {v: sum(1 for s, w, _ in found if w == v) for _, v, _ in found}
        best = max(found, key=lambda c: (c[0], repeats[c[1]]))
        others = sorted({v for _, v, _ in found if v != best[1]})
        year = fiscal_year(filed, sub.get("fiscalYearEnd"))
        note = f'DEF 14A filed {filed}, fiscal year end {sub.get("fiscalYearEnd")}; quote: "{best[2]}"'
        if others:
            note += f"; other candidate numbers in the proxy: {', '.join(f'{v:g}' for v in others[:5])}"
        for ticker in tickers:
            rows.append({"ticker": ticker, "year": year, "value": best[1], "source": SOURCE,
                         "source_url": url, "retrieved": today_utc(), "note": note})
        if n % 50 == 0:
            print(f"  {n}/{len(by_cik)} ...", flush=True)

    print(f"no DEF 14A in recent filings: {len(no_proxy)} {no_proxy[:15]}")
    print(f"DEF 14A without a recognisable pay ratio: {len(no_ratio)} {no_ratio[:40]}")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
