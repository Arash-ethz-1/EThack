"""median_worker_pay - annual total compensation of the company's median employee (USD).

What it measures: what the typical worker actually earns. Since 2018 SEC Regulation S-K
Item 402(u) requires every US-listed company to disclose, next to the CEO pay ratio, the
annual total compensation of its median employee - identified across the whole workforce
(incl. part-time and non-US staff) with the same "total compensation" definition as the
CEO's. Higher is better: a company that pays its typical worker more contributes more to
household income and the local economy. It is a per-person amount, so company size does
not matter; it is strongly industry-driven (retail and restaurants pay less than
software), so compare it within a sector.

How: the same DEF 14A proxies as social/ceo_pay_ratio (downloaded and cached by that
script's helpers into social/raw/proxies/). The first dollar amount after the disclosure's own
wording ("median employee", "median compensated employee", "median associate" ...), with no
CEO wording, percentile/average/US-only wording or other amount in between, is a candidate
(peer-comparison tables with "Median $34,917 ... 25th percentile" are therefore ignored). A value is only kept if it is CONSISTENT with
the proxy's own pay ratio: a pay ratio stated within 1,500 characters of the
median pay, multiplied by the median pay, must match a dollar amount stated anywhere in the
proxy (the CEO's total compensation, often only in the Summary Compensation Table) within
2%, and that amount must look like a CEO package (>= $250,000). That cross-check rejects the
CEO's pay, averages or peer figures read by mistake; a company whose numbers do not
reconcile is left out rather than guessed. The exact quote is stored in `note`.

Year: the fiscal year the proxy reports on (same rule as ceo_pay_ratio).

Source: SEC EDGAR DEF 14A, https://www.sec.gov/cgi-bin/browse-edgar?type=DEF+14A
Run:    python run.py build economic median_worker_pay

Output: economic/indicators/median_worker_pay.csv
Owner:  Arash
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.io import cached_download, load_universe, today_utc, write_indicator  # noqa: E402
from social.scripts.ceo_pay_ratio import (  # noqa: E402
    ARCHIVE_URL,
    SUBMISSIONS_URL,
    fiscal_year,
    to_text,
)

CATEGORY = "economic"
INDICATOR_ID = "median_worker_pay"
SOURCE = "SEC EDGAR DEF 14A (pay ratio disclosure, Item 402(u))"
PROXY_CATEGORY = "social"  # the proxies are cached by social/ceo_pay_ratio - reuse, never download twice

DOLLAR = re.compile(r"\$\s?(\d{1,3}(?:,\d{3})+|\d{4,7})(?:\.\d{2})?(?![\d,]*\d)(?!\s*(?:million|billion|thousand|k\b))", re.I)
# the disclosure's own wording - "median employee", "median compensated employee", "median associate" ...
MEDIAN_PERSON = re.compile(
    r"median\s+(?:compensated\s+|paid\s+|identified\s+)?(?:employee|associate|worker|team\s+member|colleague|individual|partner)"
    # "the median annual total compensation of all Caterpillar employees" / "median of the annual total compensation of all employees"
    r"|median\s+(?:of\s+the\s+)?(?:annual\s+)?(?:total\s+)?compensation\s+of\s+(?:all\s+)?(?:[\w&.'-]+\s+){0,3}?(?:employees|associates|team\s+members)",
    re.I,
)
CEO_WORDS = re.compile(r"\bceo\b|chief executive|president|chairman|mr\.|ms\.|named executive", re.I)
NOT_PAY = re.compile(r"percentile|threshold|less than|below|above|more than|per hour|hourly|range|average|u\.s\.|united states", re.I)
BEFORE = 300
WINDOW = 1_500  # the pay ratio and the CEO's pay must be stated within this many characters of the median pay
TOLERANCE = 0.02


def drop_parentheses(text: str) -> str:
    """'(identified from all employees worldwide, excluding our CEO)' and ', other than Mr. Creed,'
    are not about the CEO's pay."""
    text = re.sub(r"\([^()]{0,300}\)", " ", text)
    return re.sub(r",?\s*(?:other than|excluding|except(?: for)?)\s+[^,$]{0,60},", " ", text, flags=re.I)


def median_candidates(text: str) -> list[tuple[int, float, str, int]]:
    """(distance to the median-employee phrase, value, quote, position) for the FIRST dollar
    amount after a 'median employee' phrase, with no CEO wording or other amount in between."""
    out = []
    for m in DOLLAR.finditer(text):
        before = drop_parentheses(text[max(0, m.start() - BEFORE):m.start()])
        phrases = list(MEDIAN_PERSON.finditer(before))
        if not phrases:
            continue
        between = before[phrases[-1].end():]
        if CEO_WORDS.search(between) or NOT_PAY.search(before[phrases[-1].start():]) or DOLLAR.search(between):
            continue
        value = float(m.group(1).replace(",", ""))
        if not 1_000 <= value <= 1_000_000:
            continue
        quote = text[max(0, m.start() - 220):m.end() + 40].strip()
        out.append((len(between), value, quote, m.start()))
    return out


RATIO = re.compile(r"(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(?:-?\s*to\s*-?|:)\s*(?:1|one)(?![\d,]*\d)"
                   r"|(?<![\d.,])(?:1|one)\s*(?:-?\s*to\s*-?|:)\s*(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(?![\d,]*\d)", re.I)


def stated_ratios(text: str) -> list[float]:
    """Every 'N to 1' / 'N:1' / '1-to-N' in the text. Loose on purpose: a ratio only counts
    when ratio x median pay also equals a dollar amount in the proxy (see pick)."""
    out = set()
    for m in RATIO.finditer(text):
        value = float((m.group(1) or m.group(2)).replace(",", ""))
        if 1 < value <= 20_000:
            out.add(value)
    return sorted(out)


def pick(text: str) -> tuple[float, float, str] | None:
    """-> (median pay, pay ratio, quote) if a median amount reconciles with a pay ratio and a
    CEO pay amount stated close to it: ratio x median = CEO pay within 2%."""
    dollars = [float(m.group(1).replace(",", "")) for m in DOLLAR.finditer(text)]  # CEO pay is often only in the Summary Compensation Table
    for _, median, quote, pos in sorted(median_candidates(text)):
        near = text[max(0, pos - WINDOW):pos + WINDOW]
        ratios = stated_ratios(near)
        for ratio in ratios:
            implied_ceo = median * ratio
            if implied_ceo < 250_000:
                continue  # not a CEO pay package - a coincidence between two small numbers
            if any(abs(d - implied_ceo) <= TOLERANCE * implied_ceo for d in dollars if d != median):
                return median, ratio, quote
    return None


def build() -> pd.DataFrame:
    universe = load_universe()
    by_cik: dict[int, list[str]] = {}
    for t, c in zip(universe["ticker"], universe["cik"]):
        by_cik.setdefault(int(c), []).append(t)

    rows, no_proxy, unreconciled = [], [], []
    for n, (cik, tickers) in enumerate(by_cik.items(), 1):
        label = "/".join(tickers)
        sub = json.loads(cached_download(SUBMISSIONS_URL.format(cik=cik), PROXY_CATEGORY,
                                         f"submissions/CIK{cik:010d}.json", pause_s=0.12).read_text(encoding="utf-8"))
        rec = sub["filings"]["recent"]
        idx = next((i for i, f in enumerate(rec["form"]) if f == "DEF 14A"), None)
        if idx is None:
            no_proxy.append(label)
            continue
        acc, doc, filed = rec["accessionNumber"][idx], rec["primaryDocument"][idx], rec["filingDate"][idx]
        url = ARCHIVE_URL.format(cik=cik, acc=acc.replace("-", ""), name=doc)
        try:
            path = cached_download(url, PROXY_CATEGORY, f"proxies/{tickers[0]}_{acc}_{doc}", pause_s=0.12)
        except Exception as exc:  # noqa: BLE001 - one bad filing must not kill the run
            no_proxy.append(f"{label} ({exc.__class__.__name__})")
            continue
        found = pick(to_text(path.read_text(encoding="utf-8", errors="ignore")))
        if found is None:
            unreconciled.append(label)
            continue
        median, ratio, quote = found
        note = (f'DEF 14A filed {filed}; median pay reconciles with the stated pay ratio {ratio:g}:1 '
                f'(ratio x median = ${median * ratio:,.0f} found in the proxy); quote: "{quote}"')
        for ticker in tickers:
            rows.append({"ticker": ticker, "year": fiscal_year(filed, sub.get("fiscalYearEnd")), "value": median,
                         "source": SOURCE, "source_url": url, "retrieved": today_utc(), "note": note})
        if n % 100 == 0:
            print(f"  {n}/{len(by_cik)} ...", flush=True)

    print(f"no DEF 14A: {len(no_proxy)} {no_proxy[:15]}")
    print(f"median pay not found or not reconciling with the pay ratio: {len(unreconciled)} {unreconciled[:40]}")
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
