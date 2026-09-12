"""Slow FEC downloader for political_alignment: corporate PACs and their disbursements.

Why a separate script: the OpenFEC API allows ~60 requests/minute, and the full pull is
thousands of requests. `political_alignment.py` must stay fast and offline, so this
helper does the downloading once and leaves two compact CSVs behind:

  social/raw/fec_pac_matches.csv        ticker -> corporate PAC committee (with evidence)
  social/raw/fec_pac_disbursements.csv  one row per itemized PAC disbursement, dated

Source: OpenFEC API, https://api.open.fec.gov/developers/  (key in .env as FEC_API_KEY)
Run:    python social/scripts/_fec_download.py committees [--universe path/to/list.csv]
        python social/scripts/_fec_download.py match      [--universe path/to/list.csv]
        python social/scripts/_fec_download.py schedule-b [--limit N]

Raw JSON pages are cached in social/raw/fec/ (git-ignored by size, see report).

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import http_headers  # noqa: E402

CATEGORY = "social"
API = "https://api.open.fec.gov/v1"
CYCLES = [2016, 2018, 2020, 2022, 2024, 2026]  # FEC two-year transaction periods
FEC_DIR = raw_dir(CATEGORY) / "fec"
MATCHES_CSV = raw_dir(CATEGORY) / "fec_pac_matches.csv"
DISB_CSV = raw_dir(CATEGORY) / "fec_pac_disbursements.csv"
ALIASES_CSV = raw_dir(CATEGORY) / "aliases.csv"

PAUSE_S = 1.05  # the API returns X-Ratelimit-Limit 60 per rolling minute


# --------------------------------------------------------------------------- http


def api_key() -> str:
    key = os.getenv("FEC_API_KEY")  # loaded from .env by common.io's dotenv call
    if not key:
        raise SystemExit("FEC_API_KEY missing - put it in .env (never in the code)")
    return key


def redact(url: str) -> str:
    """Any api_key value in a URL becomes REDACTED before it is written anywhere."""
    return re.sub(r"(api_key=)[^&\s]+", r"\1REDACTED", url)


def cached_get(url: str, filename: str, params: dict) -> Path:
    """Cached GET with the FEC key in the X-Api-Key HEADER, not in the URL.

    Why not common.io.cached_download: it logs `resp.url` into social/raw/_downloads.csv,
    which is committed - so a key passed as an `api_key=` query parameter would land in
    git. api.data.gov (which fronts the FEC API) also accepts the key as a header, so we
    send it there and log a redacted URL. Same cache location, same log columns.
    """
    path = raw_dir(CATEGORY) / filename
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = dict(http_headers())
    headers["X-Api-Key"] = api_key()
    resp = requests.get(url, params=params, headers=headers, timeout=120)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    time.sleep(PAUSE_S)

    log = raw_dir(CATEGORY) / "_downloads.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["file", "url", "retrieved_utc", "bytes"])
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        w.writerow([filename, redact(resp.url), stamp, len(resp.content)])
    return path


def fec_json(path: str, filename: str, **params) -> dict:
    """One cached OpenFEC GET. The key never reaches the URL, the cache or the log."""
    return json.loads(cached_get(API + path, filename, params).read_text(encoding="utf-8"))


# ------------------------------------------------------------------- name matching

LEGAL_WORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd",
    "limited", "plc", "lp", "llc", "llp", "nv", "sa", "ag", "the", "holdings", "holding",
    "group", "grp", "intl", "international", "worldwide", "usa", "us", "america",
    "american", "na", "and", "of", "new", "class", "common", "stock", "trust", "reit",
    "enterprises", "industries", "systems", "solutions", "technologies", "technology",
    "partners", "plc", "se", "spa", "ab", "as", "oyj",
}
# words that follow a company name in a corporate-PAC committee name
PAC_WORDS = {
    "pac", "pacs", "political", "action", "committee", "cmte", "fund", "federal",
    "employees", "employee", "employer", "good", "government", "civic", "citizenship",
    "voice", "better", "citizens", "involvement", "participation", "responsibility",
    "active", "citizenship", "stakeholders", "associates", "people", "concerned",
    "effective", "responsible", "non", "partisan", "nonpartisan", "inc", "corp",
    "company", "co", "the", "and", "for", "of", "employees'", "usa", "us", "national",
    "political action committee",
}


def norm_tokens(name: str) -> list[str]:
    """'The Boeing Company, Inc.' -> ['boeing']  (legal noise words removed)."""
    n = name.lower().replace("&", " and ").replace("'s", "s")
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    toks = [t for t in n.split() if t and t not in LEGAL_WORDS]
    return toks


def core_name(name: str) -> str:
    return " ".join(norm_tokens(name))


def pacish_tail(tail: list[str]) -> bool:
    """True if what follows the company name in a committee name looks like a PAC label."""
    if not tail:
        return False
    return all(t in PAC_WORDS for t in tail)


def load_company_list(fallback: Path | None) -> list[dict]:
    """universe/sp500.csv when it exists; otherwise the explicit --universe fallback."""
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
        rows = [r for r in csv.DictReader(f) if r.get("ticker")]
    print(f"company list: {src} ({len(rows)} companies)")
    return rows


def load_aliases() -> dict[str, list[dict]]:
    """ticker -> [{name, kind, valid_from, valid_to}, ...] from social/raw/aliases.csv."""
    if not ALIASES_CSV.exists():
        raise FileNotFoundError(f"{ALIASES_CSV} missing - run social/scripts/_aliases.py first")
    out: dict[str, list[dict]] = {}
    with ALIASES_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out.setdefault(r["ticker"], []).append(r)
    return out


# ----------------------------------------------------------------- step 1: committees


def download_committees() -> list[dict]:
    """Every FEC committee of type Q (corporate/qualified PAC), one cached page at a time."""
    per_page, page, out = 100, 1, []
    while True:
        data = fec_json(
            "/committees/",
            f"fec/committees_q_p{page:03d}.json",
            committee_type="Q",
            per_page=per_page,
            page=page,
            sort="committee_id",
        )
        out.extend(data["results"])
        pages = data["pagination"]["pages"]
        if page == 1:
            print(f"committee_type=Q: {data['pagination']['count']} committees, {pages} pages")
        if page % 10 == 0 or page == pages:
            print(f"  page {page}/{pages} ({len(out)} committees)", flush=True)
        if page >= pages:
            break
        page += 1
    return out


def load_committees() -> list[dict]:
    files = sorted(FEC_DIR.glob("committees_q_p*.json"))
    if not files:
        return download_committees()
    out = []
    for p in files:
        out.extend(json.loads(p.read_text(encoding="utf-8"))["results"])
    return out


# --------------------------------------------------------------------- step 2: match


def match_companies(companies: list[dict], committees: list[dict]) -> list[dict]:
    """Link each ticker to corporate PAC committees, using current AND former SEC names."""
    aliases = load_aliases()

    active = [c for c in committees if set(c.get("cycles") or []) & set(CYCLES)]
    print(f"{len(active)}/{len(committees)} type-Q committees active in cycles {CYCLES[0]}-{CYCLES[-1]}")

    # index committees by the core of their own name and of their affiliated organisation
    by_affil: dict[str, list[dict]] = {}
    for c in active:
        affil = core_name(c.get("affiliated_committee_name") or "")
        if affil:
            by_affil.setdefault(affil, []).append(c)

    rows: list[dict] = []
    for comp in companies:
        ticker = comp["ticker"].strip().upper()
        names = aliases.get(ticker)
        if not names:
            names = [{"name": comp.get("name", ""), "kind": "current", "valid_from": "", "valid_to": ""}]
        seen_committees: set[str] = set()
        for alias in names:
            core = core_name(alias["name"])
            if not core:
                continue
            core_toks = core.split()
            for c in active:
                cid = c["committee_id"]
                if cid in seen_committees:
                    continue
                own = norm_tokens(c.get("name") or "")
                affil = norm_tokens(c.get("affiliated_committee_name") or "")
                rule = ""
                if affil and affil == core_toks:
                    rule = "affiliated_exact"
                elif affil[: len(core_toks)] == core_toks and len(core_toks) >= 2:
                    rule = "affiliated_prefix"
                elif own[: len(core_toks)] == core_toks and pacish_tail(own[len(core_toks):]):
                    rule = "name_prefix_pac"
                if not rule:
                    continue
                # single-token company names are the risky ones (GAP, VISA, TARGET):
                # demand FEC's own organisation link, not just a name that starts alike.
                if len(core_toks) == 1 and rule == "name_prefix_pac" and not affil:
                    rule = "name_prefix_pac_weak"
                seen_committees.add(cid)
                rows.append(
                    {
                        "ticker": ticker,
                        "committee_id": cid,
                        "committee_name": c.get("name") or "",
                        "affiliated_organisation": c.get("affiliated_committee_name") or "",
                        "organization_type": c.get("organization_type") or "",
                        "state": c.get("state") or "",
                        "cycles": "|".join(str(x) for x in sorted(set(c.get("cycles") or [])) if x in CYCLES),
                        "matched_name": alias["name"],
                        "matched_name_kind": alias["kind"],
                        "match_rule": rule,
                    }
                )
    return rows


def resolve_conflicts(rows: list[dict]) -> list[dict]:
    """A committee may only belong to one company. Keep the strongest rule, drop ties."""
    order = {"affiliated_exact": 0, "affiliated_prefix": 1, "name_prefix_pac": 2, "name_prefix_pac_weak": 3}
    by_cid: dict[str, list[dict]] = {}
    for r in rows:
        by_cid.setdefault(r["committee_id"], []).append(r)
    kept, dropped = [], []
    for cid, group in by_cid.items():
        tickers = {r["ticker"] for r in group}
        if len(tickers) == 1:
            kept.extend(group)
            continue
        group.sort(key=lambda r: order[r["match_rule"]])
        best = order[group[0]["match_rule"]]
        winners = {r["ticker"] for r in group if order[r["match_rule"]] == best}
        if len(winners) == 1:
            kept.extend([r for r in group if r["ticker"] in winners])
            dropped.extend([r for r in group if r["ticker"] not in winners])
        else:
            dropped.extend(group)  # genuinely ambiguous -> no row, never a guess
    if dropped:
        print(f"dropped {len(dropped)} committee-ticker links that were ambiguous across companies")
        for r in dropped[:10]:
            print(f"    {r['ticker']:6} {r['committee_id']} {r['committee_name'][:55]} [{r['match_rule']}]")
    return kept


def write_matches(rows: list[dict]) -> None:
    cols = [
        "ticker", "committee_id", "committee_name", "affiliated_organisation",
        "organization_type", "state", "cycles", "matched_name", "matched_name_kind",
        "match_rule",
    ]
    rows = sorted(rows, key=lambda r: (r["ticker"], r["committee_id"]))
    with MATCHES_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {MATCHES_CSV.relative_to(ROOT).as_posix()}: {len(rows)} links, "
          f"{len({r['ticker'] for r in rows})} tickers, {len({r['committee_id'] for r in rows})} committees")
    from collections import Counter
    for rule, n in Counter(r["match_rule"] for r in rows).most_common():
        print(f"  {rule:24} {n}")


# ---------------------------------------------------------------- step 3: schedule B


def download_schedule_b(committee_ids: list[str], limit: int | None = None) -> None:
    """Itemized disbursements per committee per two-year period, keyset-paginated."""
    total_pages = 0
    for i, cid in enumerate(committee_ids, 1):
        if limit and i > limit:
            break
        for cycle in CYCLES:
            last_index = last_date = None
            page = 1
            while True:
                params = dict(
                    committee_id=cid,
                    two_year_transaction_period=cycle,
                    per_page=100,
                    sort="disbursement_date",
                )
                if last_index:
                    params["last_index"] = last_index
                    params["last_disbursement_date"] = last_date
                try:
                    data = fec_json(
                        "/schedules/schedule_b/",
                        f"fec/sb/{cid}_{cycle}_p{page:03d}.json",
                        **params,
                    )
                except requests.HTTPError as exc:
                    print(f"  WARN {cid} {cycle} page {page}: {exc}")
                    break
                total_pages += 1
                res = data["results"]
                if not res:
                    break
                idx = data["pagination"].get("last_indexes") or {}
                last_index = idx.get("last_index")
                last_date = idx.get("last_disbursement_date")
                if not last_index or len(res) < 100:
                    break
                page += 1
        print(f"  {i}/{len(committee_ids)} {cid} ({total_pages} pages so far)", flush=True)


def compact_schedule_b() -> None:
    """Squeeze the cached Schedule B pages into one small CSV (the JSON is ~50x bigger)."""
    out = []
    for p in sorted((FEC_DIR / "sb").glob("*.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        for r in data.get("results", []):
            rec = r.get("recipient_committee") or {}
            out.append(
                {
                    "committee_id": r.get("committee_id") or "",
                    "disbursement_date": (r.get("disbursement_date") or "")[:10],
                    "disbursement_amount": r.get("disbursement_amount"),
                    "purpose_category": r.get("disbursement_purpose_category") or "",
                    "disbursement_type": r.get("disbursement_type") or "",
                    "recipient_committee_id": r.get("recipient_committee_id") or "",
                    "recipient_name": r.get("recipient_name") or "",
                    "recipient_party": rec.get("party") or "",
                    "recipient_committee_type": rec.get("committee_type") or "",
                    "candidate_id": r.get("candidate_id") or "",
                    "candidate_office": r.get("candidate_office") or "",
                    "sub_id": r.get("sub_id") or "",
                }
            )
    # the same transaction can appear in several cached pages (amendments, overlap)
    seen, uniq = set(), []
    for r in out:
        if r["sub_id"] and r["sub_id"] in seen:
            continue
        seen.add(r["sub_id"])
        uniq.append(r)
    with DISB_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, list(uniq[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(uniq)
    print(f"wrote {DISB_CSV.relative_to(ROOT).as_posix()}: {len(uniq)} disbursements "
          f"({len(out) - len(uniq)} duplicate sub_ids dropped)")


# ---------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step", choices=["committees", "match", "schedule-b", "compact"])
    ap.add_argument("--universe", type=Path, default=None, help="fallback company list CSV")
    ap.add_argument("--limit", type=int, default=None, help="only the first N committees")
    args = ap.parse_args()

    FEC_DIR.mkdir(parents=True, exist_ok=True)
    (FEC_DIR / "sb").mkdir(parents=True, exist_ok=True)

    if args.step == "committees":
        print(f"{len(download_committees())} committees cached in {FEC_DIR}")
    elif args.step == "match":
        rows = resolve_conflicts(match_companies(load_company_list(args.universe), load_committees()))
        write_matches(rows)
    elif args.step == "schedule-b":
        with MATCHES_CSV.open(encoding="utf-8") as f:
            cids = sorted({r["committee_id"] for r in csv.DictReader(f)})
        print(f"{len(cids)} committees to pull Schedule B for")
        download_schedule_b(cids, args.limit)
        compact_schedule_b()
    elif args.step == "compact":
        compact_schedule_b()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
