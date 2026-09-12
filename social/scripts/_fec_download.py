"""Slow FEC downloader for political_alignment: corporate PACs and their disbursements.

Why a separate script: the OpenFEC API allows ~60 requests/minute, and the full pull is
thousands of requests. `political_alignment.py` must stay fast and offline, so this
helper does the downloading once and leaves two compact CSVs behind:

  social/raw/fec_pac_matches.csv        ticker -> corporate PAC committee (with evidence)
  social/raw/fec_pac_schedule_b.csv     one row per itemized PAC disbursement, dated

SUPERSEDED for the money: the `schedule-b` step needs ~5,280 paginated requests (5+ hours)
for our 334 committees. `social/scripts/_fec_bulk.py` gets the same transactions out of 12
FEC bulk files in about 15 minutes and needs no API key at all - use that instead. Only the
`committees` and `match` steps here are still on the critical path, and they run once.

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
import threading
import time
from concurrent.futures import ThreadPoolExecutor
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
# NOT fec_pac_disbursements.csv: that name now holds the bulk-file roll-up written by
# _fec_bulk.py, which the indicator reads. This slow path keeps its own file.
DISB_CSV = raw_dir(CATEGORY) / "fec_pac_schedule_b.csv"
ALIASES_CSV = raw_dir(CATEGORY) / "aliases.csv"

PAUSE_S = 1.05  # the API returns X-Ratelimit-Limit 60 per rolling minute
WORKERS = 6  # requests are latency-bound (~2s each); the limiter below keeps 60/min

_slot_lock = threading.Lock()
_next_slot = [0.0]
_local = threading.local()


def take_slot() -> None:
    """Hand out request slots PAUSE_S apart, no matter how many threads ask."""
    with _slot_lock:
        now = time.monotonic()
        start = max(now, _next_slot[0])
        _next_slot[0] = start + PAUSE_S
    delay = start - now
    if delay > 0:
        time.sleep(delay)


def session() -> requests.Session:
    s = getattr(_local, "session", None)
    if s is None:
        s = _local.session = requests.Session()
    return s


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
    # The API throws occasional 504s ("Query timed out") and the TLS front end sometimes
    # drops a connection; a few thousand requests hit both. Retry instead of losing a run.
    for attempt in range(5):
        try:
            take_slot()
            resp = session().get(url, params=params, headers=headers, timeout=180)
            if resp.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            break
        except (requests.RequestException, OSError) as exc:
            if attempt == 4:
                raise
            wait = PAUSE_S * (2**attempt) + 2
            print(f"    retry {attempt + 1}/4 after {exc.__class__.__name__}, {wait:.0f}s", flush=True)
            time.sleep(wait)
    path.write_bytes(resp.content)

    log = raw_dir(CATEGORY) / "_downloads.csv"
    with _log_lock:
        _append_download_log(log, filename, redact(resp.url), len(resp.content))
    return path


_log_lock = threading.Lock()


def _append_download_log(log: Path, filename: str, url: str, nbytes: int) -> None:
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["file", "url", "retrieved_utc", "bytes"])
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        w.writerow([filename, url, stamp, nbytes])


def fec_json(path: str, filename: str, **params) -> dict:
    """One cached OpenFEC GET. The key never reaches the URL, the cache or the log."""
    return json.loads(cached_get(API + path, filename, params).read_text(encoding="utf-8"))


# ------------------------------------------------------------------- name matching

# Only true legal-form words. Descriptive words stay: stripping "technologies" turns
# "United Technologies" into "United", which then matches United Airlines and UPS.
LEGAL_WORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies", "ltd",
    "limited", "plc", "lp", "llc", "llp", "nv", "sa", "ag", "se", "spa", "ab", "oyj",
    "the", "and", "of", "na", "cos",
}
# Trailing filler that is dropped only while something else is left, so
# "ExxonMobil Holdings Corp" and "Exxon Mobil Corporation" become the same company.
TRAILING_FILLER = {"holdings", "holding", "class", "common", "stock", "new"}
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


# SEC legal names carry the state of incorporation: "QUALCOMM INC/DE", "CLOROX CO /DE/",
# "VALERO ENERGY CORP/TX". Left in, that stray token blocks every otherwise perfect match.
STATE_SUFFIX = re.compile(r"\s*/\s*[A-Za-z]{2}\s*/?\s*(?=$|,)")


def norm_tokens(name: str) -> list[str]:
    """'The Boeing Company, Inc.' -> ['boeing']  (legal noise words removed)."""
    n = STATE_SUFFIX.sub(" ", name)
    n = n.lower().replace("&", " and ").replace("'s", "s")
    n = re.sub(r"[^a-z0-9 ]+", " ", n)
    toks = [t for t in n.split() if t and t not in LEGAL_WORDS]
    while len(toks) > 1 and toks[-1] in TRAILING_FILLER:
        toks.pop()
    return toks


def squash(toks: list[str]) -> str:
    """'exxon mobil' and 'exxonmobil' are the same company written two ways."""
    return "".join(toks)


def contains_seq(hay: list[str], needle: list[str]) -> bool:
    n = len(needle)
    return n > 0 and any(hay[i : i + n] == needle for i in range(len(hay) - n + 1))


def core_name(name: str) -> str:
    return " ".join(norm_tokens(name))


def pacish_tail(tail: list[str]) -> bool:
    """True if what follows the company name in a committee name looks like a PAC label."""
    if not tail:
        return False
    return all(t in PAC_WORDS for t in tail)


# Hand-checked rejects: committees the rules link to a company that a human confirmed is a
# DIFFERENT firm which merely starts with the same word. Every one of the 70 non-exact
# links was read by hand; these 12 were wrong. A blocklist, not a guess - see the report.
MANUAL_REJECT = {
    ("CMI", "C00408914"): "Cummins-Allison Corp (currency handling) is not Cummins Inc",
    ("LHX", "C00086256"): "BMO Harris Bank is not L3Harris",
    ("PTC", "C00717900"): "PTC Therapeutics is not PTC Inc",
    ("WMB", "C00039206"): "Williams & Jensen PLLC (law firm) is not Williams Companies",
    ("COO", "C00370270"): "Cooper Tire & Rubber (sponsor: Goodyear) is not Cooper Companies",
    ("COO", "C00553099"): "Mr. Cooper Group (mortgages) is not Cooper Companies",
    ("SO", "C00139451"): "Kansas City Southern (railroad) is not Southern Company",
    ("SO", "C00217877"): "Southern Glazer's Wine & Spirits is not Southern Company",
    ("WAT", "C00302943"): "Nestle Waters North America is not Waters Corporation",
    ("XYZ", "C00188177"): "H&R Block is not Block, Inc.",
    ("KO", "C00347989"): "Coca-Cola Bottling Company United is an independent bottler",
    ("KO", "C00540104"): "Coca-Cola Consolidated is an independent bottler",
}


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


# A former name only helps if the company still carried it near our window - a PAC keeps
# the old name for a while after a rename. Older names actively hurt: Citigroup's CIK was
# "TRAVELERS GROUP INC" until 1998, which otherwise matches today's Travelers PAC.
ALIAS_MIN_VALID_TO = "2014-01-01"


def load_aliases() -> dict[str, list[dict]]:
    """ticker -> [{name, kind, valid_from, valid_to}, ...] from social/raw/aliases.csv."""
    if not ALIASES_CSV.exists():
        raise FileNotFoundError(f"{ALIASES_CSV} missing - run social/scripts/_aliases.py first")
    out: dict[str, list[dict]] = {}
    stale = 0
    with ALIASES_CSV.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["kind"] == "former" and (r["valid_to"] or "") < ALIAS_MIN_VALID_TO:
                stale += 1
                continue
            out.setdefault(r["ticker"], []).append(r)
    print(f"aliases: dropped {stale} former names that expired before {ALIAS_MIN_VALID_TO}")
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
    # organization_type C = Corporation. Dropping the rest removes union PACs (Southwest
    # Airlines PILOTS Association), trade-association PACs (US APPLE Association - the
    # classic Apple false positive) and leadership PACs whose sponsor happens to be named
    # like a company (MCCORMICK for MKC). It costs no genuine corporate PAC we could find.
    active = [c for c in active if (c.get("organization_type") or "") == "C"]
    print(f"{len(active)} of those are organization_type C (corporation)")

    # index committees by the core of their own name and of their affiliated organisation
    by_affil: dict[str, list[dict]] = {}
    for c in active:
        affil = core_name(c.get("affiliated_committee_name") or "")
        if affil:
            by_affil.setdefault(affil, []).append(c)

    rows: list[dict] = []
    rejected: list[str] = []
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
                if affil and (affil == core_toks or squash(affil) == squash(core_toks)):
                    rule = "affiliated_exact"
                elif affil[: len(core_toks)] == core_toks:
                    # FEC's own link to the sponsoring organisation, with extra words:
                    # "ALLSTATE CORP" -> affiliated org "ALLSTATE INSURANCE CO."
                    rule = "affiliated_prefix" if len(core_toks) >= 2 else "affiliated_prefix_1tok"
                elif own[: len(core_toks)] == core_toks and pacish_tail(own[len(core_toks):]):
                    rule = "name_prefix_pac"
                elif contains_seq(own, core_toks) and any(w in own for w in ("pac", "political")):
                    # "EMPLOYEES OF NORTHROP GRUMMAN CORPORATION PAC" - name does not start
                    # with the company, but the company is spelled out inside it.
                    rule = "name_contains_pac"
                if not rule:
                    continue
                # single-token company names are the risky ones (GAP, VISA, TARGET):
                # demand FEC's own organisation link, not just a name that starts alike.
                if len(core_toks) == 1 and rule in ("name_prefix_pac", "name_contains_pac"):
                    # "GAP", "BANK", "VISA" inside a committee name prove nothing
                    if len(core_toks[0]) < 5:
                        continue
                    if not affil:
                        rule += "_weak"
                seen_committees.add(cid)
                if (ticker, cid) in MANUAL_REJECT:
                    rejected.append(f"{ticker} {cid}: {MANUAL_REJECT[(ticker, cid)]}")
                    continue
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
    print(f"hand-checked blocklist removed {len(rejected)} wrong links:")
    for r in rejected:
        print(f"    {r}")
    return rows


def resolve_conflicts(rows: list[dict], cik_of: dict[str, str]) -> list[dict]:
    """A committee may only belong to one company. Keep the strongest rule, drop ties.

    Two tickers of the same company (FOX/FOXA, GOOG/GOOGL) share a CIK - that is one
    company with two share classes, not a conflict, so both keep the link.
    """
    order = {
        "affiliated_exact": 0, "affiliated_prefix": 1, "affiliated_prefix_1tok": 2,
        "name_prefix_pac": 3, "name_contains_pac": 4,
        "name_prefix_pac_weak": 5, "name_contains_pac_weak": 6,
    }
    by_cid: dict[str, list[dict]] = {}
    for r in rows:
        by_cid.setdefault(r["committee_id"], []).append(r)
    kept, dropped = [], []
    for cid, group in by_cid.items():
        tickers = {r["ticker"] for r in group}
        if len(tickers) == 1 or len({cik_of.get(t, t) for t in tickers}) == 1:
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


def review_unmatched(companies: list[dict], committees: list[dict], matched: list[dict]) -> None:
    """List loose look-alikes for every unmatched company, so misses can be hand-checked."""
    aliases = load_aliases()
    done = {r["ticker"] for r in matched}
    active = [c for c in committees if set(c.get("cycles") or []) & set(CYCLES)]
    out = []
    for comp in companies:
        ticker = comp["ticker"].strip().upper()
        if ticker in done:
            continue
        names = aliases.get(ticker) or [{"name": comp.get("name", "")}]
        cands = []
        for alias in names:
            toks = norm_tokens(alias["name"])
            if not toks or len(toks[0]) < 4:
                continue
            head = toks[0]
            for c in active:
                blob = core_name(c.get("name") or "") + " " + core_name(c.get("affiliated_committee_name") or "")
                if head in blob.split():
                    cands.append(f"{c['committee_id']}:{(c.get('name') or '')[:50]}")
        out.append({"ticker": ticker, "name": comp.get("name", ""),
                    "candidates": " | ".join(sorted(set(cands))[:4])})
    path = raw_dir(CATEGORY) / "fec_pac_unmatched_review.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["ticker", "name", "candidates"], lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    withc = sum(1 for r in out if r["candidates"])
    print(f"wrote {path.relative_to(ROOT).as_posix()}: {len(out)} unmatched companies, "
          f"{withc} of them have a loose look-alike committee worth a human look")


# ---------------------------------------------------------------- step 3: schedule B


KEEP_FIELDS = (
    "disbursement_date", "disbursement_amount", "disbursement_purpose_category",
    "disbursement_type", "recipient_committee_id", "recipient_name", "candidate_id",
    "candidate_office", "sub_id",
)


def _compact_row(r: dict) -> dict:
    rec = r.get("recipient_committee") or {}
    out = {k: r.get(k) for k in KEEP_FIELDS}
    out["disbursement_date"] = (out["disbursement_date"] or "")[:10]
    out["recipient_party"] = rec.get("party") or ""
    out["recipient_committee_type"] = rec.get("committee_type") or ""
    return out


def _pull_period(cid: str, cycle: int, out_dir: Path) -> int:
    """All Schedule B pages for one committee in one two-year period -> one small file."""
    target = out_dir / f"{cid}_{cycle}.json"
    if target.exists():
        return 0
    rows, last_index, last_date, page, pages = [], None, None, 1, 0
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
        tmp = out_dir / f"_tmp_{cid}_{cycle}_p{page:03d}.json"
        try:
            data = json.loads(
                cached_get(API + "/schedules/schedule_b/", f"fec/sb/{tmp.name}", params)
                .read_text(encoding="utf-8")
            )
        except Exception as exc:  # noqa: BLE001 - one bad period must not kill the run
            print(f"  WARN {cid} {cycle} page {page}: {exc.__class__.__name__}", flush=True)
            return pages
        finally:
            tmp.unlink(missing_ok=True)
        pages += 1
        res = data.get("results") or []
        rows.extend(_compact_row(r) for r in res)
        idx = data["pagination"].get("last_indexes") or {}
        last_index, last_date = idx.get("last_index"), idx.get("last_disbursement_date")
        if len(res) < 100 or not last_index:
            break
        page += 1
    target.write_text(json.dumps(rows), encoding="utf-8")
    return pages


def download_schedule_b(committee_ids: list[str], limit: int | None = None) -> None:
    """Itemized disbursements per committee per two-year period.

    Each raw page is ~450 KB because every row embeds the full filer and recipient
    committee objects; the full pull would be ~1.5 GB. So each page is compacted to the
    dozen fields we use and only the compacted per-committee-cycle file is kept - that
    file is also the cache marker, so a re-run never downloads the same period twice.

    One committee-period is one task. Pagination inside a period is keyset-based and has
    to stay serial, but different periods are independent, so a few threads share the
    one request-per-second budget and the run stops being latency-bound.
    """
    out_dir = FEC_DIR / "sb"
    out_dir.mkdir(parents=True, exist_ok=True)
    todo = committee_ids[:limit] if limit else committee_ids
    tasks = [(cid, cycle) for cid in todo for cycle in CYCLES]
    tasks = [(cid, cyc) for cid, cyc in tasks if not (out_dir / f"{cid}_{cyc}.json").exists()]
    print(f"{len(tasks)} committee-periods to download ({len(todo)} committees x {len(CYCLES)} periods)")
    done = pages = 0
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(_pull_period, cid, cyc, out_dir) for cid, cyc in tasks]
        for fut in futures:
            pages += fut.result()
            done += 1
            if done % 25 == 0 or done == len(tasks):
                mins = (time.monotonic() - started) / 60
                rate = pages / mins if mins else 0
                left = (len(tasks) - done) / (done / mins) if done and mins else 0
                print(f"  {done}/{len(tasks)} periods, {pages} pages, "
                      f"{rate:.0f} req/min, ~{left:.0f} min left", flush=True)


def compact_schedule_b() -> None:
    """Merge the per-committee-cycle files into one CSV that the indicator script reads."""
    cols = [
        "committee_id", "disbursement_date", "disbursement_amount", "purpose_category",
        "disbursement_type", "recipient_committee_id", "recipient_name",
        "recipient_party", "recipient_committee_type", "candidate_id",
        "candidate_office", "sub_id",
    ]
    seen, out = set(), []
    for p in sorted((FEC_DIR / "sb").glob("*.json")):
        if p.name.startswith("_tmp_"):
            continue
        cid = p.stem.split("_")[0]
        for r in json.loads(p.read_text(encoding="utf-8")):
            sub = r.get("sub_id") or ""
            if sub and sub in seen:
                continue  # the same transaction shows up in several two-year periods
            seen.add(sub)
            out.append({
                "committee_id": cid,
                "disbursement_date": r.get("disbursement_date") or "",
                "disbursement_amount": r.get("disbursement_amount"),
                "purpose_category": r.get("disbursement_purpose_category") or "",
                "disbursement_type": r.get("disbursement_type") or "",
                "recipient_committee_id": r.get("recipient_committee_id") or "",
                "recipient_name": r.get("recipient_name") or "",
                "recipient_party": r.get("recipient_party") or "",
                "recipient_committee_type": r.get("recipient_committee_type") or "",
                "candidate_id": r.get("candidate_id") or "",
                "candidate_office": r.get("candidate_office") or "",
                "sub_id": sub,
            })
    with DISB_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, cols, lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    print(f"wrote {DISB_CSV.relative_to(ROOT).as_posix()}: {len(out)} itemized disbursements "
          f"from {len({r['committee_id'] for r in out})} committees")


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
        companies = load_company_list(args.universe)
        cik_of = {c["ticker"].strip().upper(): (c.get("cik") or "").lstrip("0") for c in companies}
        rows = resolve_conflicts(match_companies(companies, load_committees()), cik_of)
        write_matches(rows)
        review_unmatched(companies, load_committees(), rows)
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
