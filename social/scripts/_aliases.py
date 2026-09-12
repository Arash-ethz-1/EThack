"""Company name aliases per ticker, so text searches find a company under its old name.

Why this exists: `universe/sp500.csv` holds *display* names. A 2019 court-docket search
for "Meta Platforms" finds almost nothing, because the company was "Facebook Inc" until
2021-10-27. SEC's submissions API returns `formerNames` **with valid-from/to dates**, so
the correct name for any point in time can be resolved automatically.

Source: https://data.sec.gov/submissions/CIK##########.json
Run:    python social/scripts/_aliases.py [--universe path/to/list.csv]

Output: social/raw/aliases.csv  (ticker, cik, name, valid_from, valid_to, kind)

The 503 downloaded submission files total ~83 MB, so they are cached in
social/raw/submissions/ and git-ignored. Only the small derived CSV is committed.
Re-running this script recreates everything from scratch.

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import cached_download  # noqa: E402

CATEGORY = "social"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
OUT = raw_dir(CATEGORY) / "aliases.csv"


def load_company_list(fallback: Path | None) -> list[dict]:
    """universe/sp500.csv when Arash has built it; otherwise an explicit fallback list."""
    from common.config import UNIVERSE_CSV

    if UNIVERSE_CSV.exists():
        src = UNIVERSE_CSV
    elif fallback and fallback.exists():
        src = fallback
        print(f"WARN universe/sp500.csv does not exist yet (Arash) - using {src}")
        print("WARN re-run this once the real universe lands; tickers must match it exactly.")
    else:
        raise FileNotFoundError(
            "universe/sp500.csv does not exist yet and no --universe fallback was given"
        )
    with src.open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("cik")]
    print(f"company list: {src} ({len(rows)} companies)")
    return rows


def normalise(name: str) -> str:
    """Loose form used only to spot duplicates: 'CITIGROUP INC' == 'Citigroup Inc.'"""
    n = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    n = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|lp|llc|sa|nv|the|new|de|md)\b", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def iso_date(value: str | None) -> str:
    """'2021-10-27T04:00:00.000Z' -> '2021-10-27'; None/'' -> ''."""
    return (value or "")[:10]


def build(companies: list[dict]) -> list[dict]:
    out: list[dict] = []
    missing: list[str] = []
    for i, row in enumerate(companies, 1):
        ticker, cik = row["ticker"].strip().upper(), int(row["cik"])
        try:
            path = cached_download(
                SUBMISSIONS_URL.format(cik=cik),
                CATEGORY,
                f"submissions/CIK{cik:010d}.json",
                pause_s=0.12,  # SEC allows 10 requests/second
            )
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - one bad CIK must not kill the run
            missing.append(f"{ticker} ({exc.__class__.__name__})")
            continue

        out.append(
            {
                "ticker": ticker,
                "cik": f"{cik:010d}",
                "name": data.get("name", "").strip(),
                "valid_from": "",
                "valid_to": "",
                "kind": "current",
            }
        )
        for former in data.get("formerNames") or []:
            out.append(
                {
                    "ticker": ticker,
                    "cik": f"{cik:010d}",
                    "name": (former.get("name") or "").strip(),
                    "valid_from": iso_date(former.get("from")),
                    "valid_to": iso_date(former.get("to")),
                    "kind": "former",
                }
            )
        if i % 50 == 0:
            print(f"  {i}/{len(companies)} ...", flush=True)

    if missing:
        print(f"WARN no submissions data for {len(missing)}: {', '.join(missing[:10])}")

    # EDGAR re-registers identical names (e.g. "CITIGROUP INC" -> "CITIGROUP INC"), which
    # adds rows that are useless for searching. Keep only names that really differ from the
    # company's current name, and drop exact duplicates.
    current = {r["ticker"]: normalise(r["name"]) for r in out if r["kind"] == "current"}
    kept, seen, dropped = [], set(), 0
    for r in out:
        if not r["name"]:
            continue
        key = (r["ticker"], normalise(r["name"]))
        if r["kind"] == "former" and (normalise(r["name"]) == current.get(r["ticker"]) or key in seen):
            dropped += 1
            continue
        seen.add(key)
        kept.append(r)
    print(f"dropped {dropped} former names identical to the current name or duplicated")
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--universe", type=Path, default=None, help="fallback company list CSV")
    args = ap.parse_args()

    rows = build(load_company_list(args.universe))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["ticker", "cik", "name", "valid_from", "valid_to", "kind"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    tickers = {r["ticker"] for r in rows}
    formers = [r for r in rows if r["kind"] == "former"]
    renamed = {r["ticker"] for r in formers}
    print(f"\nwrote {OUT.relative_to(ROOT).as_posix()}: {len(rows)} names, {len(tickers)} tickers")
    print(f"  {len(renamed)} companies have at least one former name ({len(formers)} former names)")
    print("  without this, text searches silently miss those companies before the rename.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
