"""Subsidiary names per company, from Exhibit 21 of its latest 10-K.

Why this exists: government datasets list the legal entity that filed, not the parent.
Amazon's warehouses report to OSHA as "Amazon.com Services LLC", McDonald's 401(k) plan
is sponsored by "McDonald's USA, LLC". Exhibit 21 ("Subsidiaries of the registrant") is
the company's own list of those entities, so matching against it finds them without
guessing.

Source: SEC EDGAR, latest 10-K per company (submissions API -> filing index headers -> EX-21)
Run:    python social/scripts/_subsidiaries.py

Output: social/raw/subsidiaries.csv  (ticker, cik, subsidiary, source_url)

The raw submissions and EX-21 files are cached in social/raw/submissions/ and
social/raw/exhibit21/ (git-ignored); only the small derived CSV is committed.

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import cached_download, load_universe  # noqa: E402

CATEGORY = "social"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{name}"
OUT = raw_dir(CATEGORY) / "subsidiaries.csv"

# A line is taken as an entity name only if it carries a legal-form word.
LEGAL_FORM = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|llc|l\.l\.c|lp|l\.p|llp|plc|"
    r"gmbh|ag|bv|b\.v|nv|n\.v|sa|s\.a|sas|sarl|s\.a\.r\.l|srl|s\.r\.l|spa|s\.p\.a|kk|pty|pte|"
    r"trust|partnership|holdings?)\b\.?",
    re.IGNORECASE,
)


def submissions(cik: int) -> dict:
    path = cached_download(
        SUBMISSIONS_URL.format(cik=cik), CATEGORY, f"submissions/CIK{cik:010d}.json", pause_s=0.12
    )
    return json.loads(path.read_text(encoding="utf-8"))


def latest_filing(sub: dict, forms: tuple[str, ...]) -> dict | None:
    """Most recent filing of one of `forms` in the submissions 'recent' block."""
    rec = sub["filings"]["recent"]
    for i, form in enumerate(rec["form"]):  # newest first
        if form in forms:
            return {k: rec[k][i] for k in ("accessionNumber", "filingDate", "primaryDocument", "reportDate")}
    return None


def exhibit_files(index_headers: str, exhibit: str) -> list[str]:
    """File names of one exhibit type, from a filing's '-index-headers.html' SGML header.

    File names are free-form ('a10-kexhibit21109272025.htm', 'subsidiariesofabbott.htm'),
    but the <TYPE> line is not: EX-21, EX-21.1, ...
    """
    text = html.unescape(index_headers)
    pairs = re.findall(r"<TYPE>([^\s<]+)\s*(?:<[^>]+>[^<]*\s*)*?<FILENAME>([^\s<]+)", text)
    return [name for typ, name in pairs if typ.upper().startswith(exhibit)]


def html_to_lines(raw: str) -> list[str]:
    """Cell/paragraph-level text lines of an HTML (or plain text) exhibit."""
    raw = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)</?(td|th|tr|p|div|br|li|table)[^>]*>", "\n", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = text.replace("\xa0", " ").replace("\u200b", "")
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]


def entity_names(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        # "Apple Operations International Limited ......... Ireland" -> drop leader dots + place
        line = re.split(r"\s*\.{3,}\s*|\s{3,}|\t", line)[0].strip(" ,;*()")
        line = re.sub(r"\s*[(\[][^)\]]*[)\]]\s*$", "", line)  # trailing "(Delaware)" / "[100%]"
        if 4 <= len(line) <= 120 and LEGAL_FORM.search(line):
            out.append(line)
    return list(dict.fromkeys(out))


def main() -> int:
    universe = load_universe()
    rows, no_10k, no_ex21 = [], [], []
    by_cik: dict[int, list[str]] = {}
    for t, c in zip(universe["ticker"], universe["cik"]):
        by_cik.setdefault(int(c), []).append(t)

    for n, (cik, tickers) in enumerate(by_cik.items(), 1):
        label = "/".join(tickers)
        try:
            filing = latest_filing(submissions(cik), ("10-K",))
            if filing is None:
                no_10k.append(label)
                continue
            acc = filing["accessionNumber"].replace("-", "")
            headers = cached_download(
                ARCHIVE_URL.format(cik=cik, acc=acc, name=f"{filing['accessionNumber']}-index-headers.html"),
                CATEGORY,
                f"exhibit21/{tickers[0]}_{filing['accessionNumber']}_headers.html",
                pause_s=0.12,
            ).read_text(encoding="utf-8", errors="ignore")
            ex21 = exhibit_files(headers, "EX-21")
            if not ex21:
                no_ex21.append(label)
                continue
            url = ARCHIVE_URL.format(cik=cik, acc=acc, name=ex21[0])
            raw = cached_download(url, CATEGORY, f"exhibit21/{tickers[0]}_{ex21[0]}", pause_s=0.12)
            subs = entity_names(html_to_lines(raw.read_text(encoding="utf-8", errors="ignore")))
        except Exception as exc:  # noqa: BLE001 - one bad filing must not kill the run
            no_ex21.append(f"{label} ({exc.__class__.__name__})")
            continue
        for ticker in tickers:
            rows += [{"ticker": ticker, "cik": f"{cik:010d}", "subsidiary": s, "source_url": url} for s in subs]
        if n % 50 == 0:
            print(f"  {n}/{len(by_cik)} ...", flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["ticker", "cik", "subsidiary", "source_url"], lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    found = {r["ticker"] for r in rows}
    print(f"wrote {OUT.relative_to(ROOT).as_posix()}: {len(rows)} names, {len(found)} tickers")
    print(f"  no 10-K in recent filings: {len(no_10k)} {no_10k[:10]}")
    print(f"  no EX-21 attached (often incorporated by reference): {len(no_ex21)} {no_ex21[:10]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
