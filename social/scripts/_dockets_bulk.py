"""Extract labor dockets for the S&P 500 from CourtListener's bulk dump.

Why this exists: CourtListener's authenticated search API allows 5 requests/minute, so
fetching 503 companies takes hours. Their bulk dump is 4.88 GB (measured 3.47 MB/s, ~23
min) and has no rate limit at all.

Trade-off: the dump carries `case_name` and `case_name_full` but NO party list, so
matching moves from party names to case names. The companies already fetched through the
API are kept as a validation set to measure exactly what that costs.

Source: https://storage.courtlistener.com/bulk-data/dockets-<date>.csv.bz2
Run:    python social/scripts/_dockets_bulk.py --dump /path/to/dockets.csv.bz2

Output: social/raw/dockets_bulk/<TICKER>.json, same shape as social/raw/dockets/.
Leading underscore: `python run.py build social` skips it.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import UNIVERSE_CSV, raw_dir  # noqa: E402
from _dockets import WINDOW_FROM, WINDOW_TO, core, is_ambiguous, is_labor  # noqa: E402

CATEGORY = "social"
OUT_DIR = raw_dir(CATEGORY) / "dockets_bulk"

# Column positions in the bulk dockets CSV, verified against its header row.
COL_ID, COL_DATE_FILED, COL_CASE_NAME, COL_CASE_NAME_FULL = 0, 14, 18, 19
COL_NOS, COL_COURT = 25, 42

# Cheap pre-filter: skip rows that cannot be a labor case before paying for matching.
CHEAP = re.compile(r"Labor|Civil Rights|Disabilit|Fair Standards|E\.R\.I\.S\.A", re.I)
SPLIT_V = re.compile(r"\s+v(?:s?\.?|ersus)\s+", re.I)


def company_cores() -> dict[str, list[str]]:
    """ticker -> search cores, from the universe plus the alias table."""
    aliases = defaultdict(list)
    alias_path = raw_dir(CATEGORY) / "aliases.csv"
    if alias_path.exists():
        with alias_path.open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["kind"] == "current" or (r["valid_to"] or "") >= WINDOW_FROM:
                    aliases[r["ticker"]].append(r["name"])
    out: dict[str, list[str]] = {}
    with UNIVERSE_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t = r["ticker"].strip().upper()
            seen, keep = set(), []
            for n in [r["name"], *aliases.get(t, [])]:
                c = core(n)
                if len(c) >= 2 and c not in seen:
                    seen.add(c)
                    keep.append(c)
            if keep:
                out[t] = keep
    return out


def build_index(cores: dict[str, list[str]]) -> dict[str, list[tuple[str, str]]]:
    """First word of each core -> [(ticker, core)], so matching is a dict hit not a scan."""
    idx: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for ticker, names in cores.items():
        for c in names:
            idx[c.split()[0]].append((ticker, c))
    return idx


def match_party(text: str, idx: dict) -> set[str]:
    """Tickers whose name appears as a party in this case name."""
    hits: set[str] = set()
    for side in SPLIT_V.split(text):
        c = core(side)
        if not c:
            continue
        words = c.split()
        for i in range(len(words)):
            for ticker, name in idx.get(words[i], ()):
                rest = " ".join(words[i:])
                if rest == name:
                    hits.add(ticker)
                elif rest.startswith(name + " ") and not is_ambiguous(name):
                    hits.add(ticker)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", type=Path, required=True)
    ap.add_argument("--progress-every", type=int, default=2_000_000)
    args = ap.parse_args()

    cores = company_cores()
    idx = build_index(cores)
    print(f"universe: {len(cores)} companies, {sum(len(v) for v in cores.values())} search names")

    found: dict[str, list[dict]] = defaultdict(list)
    rows = kept = 0
    started = time.time()
    csv.field_size_limit(10_000_000)
    with bz2.open(args.dump, "rt", encoding="utf-8", errors="ignore", newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header
        for row in reader:
            rows += 1
            if rows % args.progress_every == 0:
                print(f"  {rows / 1e6:.0f}M rows, {kept} labor dockets matched, "
                      f"{time.time() - started:.0f}s", flush=True)
            if len(row) <= COL_COURT:
                continue
            nos = row[COL_NOS]
            if not nos or not CHEAP.search(nos) or not is_labor(nos):
                continue
            filed = row[COL_DATE_FILED]
            if len(filed) < 10 or not (WINDOW_FROM <= filed[:10] < WINDOW_TO):
                continue
            name = row[COL_CASE_NAME_FULL] or row[COL_CASE_NAME]
            if not name:
                continue
            for ticker in match_party(name, idx):
                found[ticker].append({
                    "docket_id": row[COL_ID], "caseName": row[COL_CASE_NAME],
                    "dateFiled": filed[:10], "suitNature": nos, "court": row[COL_COURT],
                })
                kept += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for ticker, dockets in found.items():
        (OUT_DIR / f"{ticker}.json").write_text(
            json.dumps({"ticker": ticker, "names": cores[ticker], "source": "bulk",
                        "dockets": dockets}), encoding="utf-8")
    print(f"\nscanned {rows:,} rows in {time.time() - started:.0f}s")
    print(f"matched {kept:,} labor dockets across {len(found)}/{len(cores)} companies "
          f"= {100 * len(found) / len(cores):.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
