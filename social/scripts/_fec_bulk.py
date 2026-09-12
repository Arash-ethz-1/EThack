"""Fast FEC downloader for political_alignment: bulk transaction files, no API key.

Why bulk instead of the API: the OpenFEC Schedule B endpoint needs ~5,280 paginated
requests (~1,641 rows per committee at 100 rows/page) for our 334 corporate PACs, which
is 5+ hours at the 60 requests/minute limit. The FEC publishes the same transactions as
pipe-delimited bulk files, two per two-year cycle, so 12 downloads replace 5,280 calls.
These files need NO API key at all.

  pas2{YY}.zip  contributions FROM committees TO candidates
  oth{YY}.zip   any transaction from one committee to another
  cm{YY}.zip    committee master - gives us the recipient committee's party and type
  cn{YY}.zip    candidate master - gives us the recipient candidate's party and office

File layouts (positional, no header row) are taken from the FEC's own descriptions:
  https://www.fec.gov/campaign-finance-data/contributions-committees-candidates-file-description/
  https://www.fec.gov/campaign-finance-data/any-transaction-one-committee-another-file-description/
  https://www.fec.gov/campaign-finance-data/committee-master-file-description/
  https://www.fec.gov/campaign-finance-data/candidate-master-file-description/

Outputs:
  social/raw/fec_pac_disbursements.csv  one row per itemized transaction of a matched PAC
  social/raw/fec_pac_coverage.csv       per ticker: was its money actually downloaded, or
                                        does the company genuinely have no corporate PAC,
                                        or could we not tell? (AGENTS.md 4.6: a missing
                                        company must stay a missing row, never a zero)

Run:  python social/scripts/_fec_bulk.py            # download + parse (needs fec_pac_matches.csv)
      python social/scripts/_fec_bulk.py --parse-only

The zips live in social/raw/fec_bulk/ and are git-ignored by size; everything the
indicator needs is in the two CSVs above, which are committed.

Leading underscore = `python run.py build social` skips this; it is a helper, not an
indicator.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import cached_download  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _fec_download import CYCLES, core_name, load_aliases, load_company_list  # noqa: E402

CATEGORY = "social"
RAW = raw_dir(CATEGORY)
BULK_DIR = RAW / "fec_bulk"
MATCHES_CSV = RAW / "fec_pac_matches.csv"
DISB_CSV = RAW / "fec_pac_disbursements.csv"        # compact, committed
TX_CSV = RAW / "fec_pac_transactions.csv"           # full detail, git-ignored
COVERAGE_CSV = RAW / "fec_pac_coverage.csv"

BULK_BASE = "https://www.fec.gov/files/bulk-downloads"
SOURCE_URL = "https://www.fec.gov/data/browse-data/?tab=bulk-data"

# Positional layouts, straight from the FEC file descriptions linked in the docstring.
PAS2_COLS = [
    "cmte_id", "amndt_ind", "rpt_tp", "transaction_pgi", "image_num", "transaction_tp",
    "entity_tp", "name", "city", "state", "zip_code", "employer", "occupation",
    "transaction_dt", "transaction_amt", "other_id", "cand_id", "tran_id", "file_num",
    "memo_cd", "memo_text", "sub_id",
]
# identical to PAS2 except that OTH has no cand_id column
OTH_COLS = [c for c in PAS2_COLS if c != "cand_id"]
CM_COLS = [
    "cmte_id", "cmte_nm", "tres_nm", "cmte_st1", "cmte_st2", "cmte_city", "cmte_st",
    "cmte_zip", "cmte_dsgn", "cmte_tp", "cmte_pty_affiliation", "cmte_filing_freq",
    "org_tp", "connected_org_nm", "cand_id",
]
CN_COLS = [
    "cand_id", "cand_name", "cand_pty_affiliation", "cand_election_yr", "cand_office_st",
    "cand_office", "cand_office_district", "cand_ici", "cand_status", "cand_pcc",
    "cand_st1", "cand_st2", "cand_city", "cand_st", "cand_zip",
]

YEAR_MIN, YEAR_MAX = 2015, 2026  # cycles 2016..2026 cover 2015-01-01 .. 2026-12-31

# Minnesota's Democratic-Farmer-Labor party IS the Democratic party there; the FEC codes
# it separately. Everything else keeps its own code (IND, LIB, GRE, ...).
PARTY_ALIAS = {"DFL": "DEM"}


# ------------------------------------------------------------------------ download


def bulk_files() -> list[tuple[str, str]]:
    """[(local filename, url), ...] for all four file kinds across all six cycles."""
    out = []
    for cycle in CYCLES:
        yy = f"{cycle % 100:02d}"
        for stem in (f"pas2{yy}", f"oth{yy}", f"cm{yy}", f"cn{yy}"):
            out.append((f"fec_bulk/{stem}.zip", f"{BULK_BASE}/{cycle}/{stem}.zip"))
    return out


def download_all() -> None:
    """Fetch every bulk zip once. No API key is involved, so nothing can leak into the log."""
    BULK_DIR.mkdir(parents=True, exist_ok=True)
    total = 0
    for filename, url in bulk_files():
        path = cached_download(url, CATEGORY, filename, pause_s=0.5)
        total += path.stat().st_size
    print(f"bulk cache: {len(bulk_files())} files, {total / 1e6:.0f} MB in "
          f"{BULK_DIR.relative_to(ROOT).as_posix()}")


def rows_of(stem: str, cols: list[str]):
    """Stream one bulk zip as dicts. The files have NO header row and are '|'-delimited."""
    path = BULK_DIR / f"{stem}.zip"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run: python social/scripts/_fec_bulk.py")
    with zipfile.ZipFile(path) as zf:
        inner = zf.namelist()[0]
        with zf.open(inner) as fh:
            text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline="")
            for line in text:
                parts = line.rstrip("\r\n").split("|")
                if len(parts) < len(cols):
                    continue
                yield dict(zip(cols, parts))


# --------------------------------------------------------------------------- dates


def parse_date(mmddyyyy: str) -> str:
    """FEC bulk dates are MMDDYYYY. Returns 'YYYY-MM-DD', or '' if it is not a real date."""
    s = (mmddyyyy or "").strip()
    if len(s) != 8 or not s.isdigit():
        return ""
    mm, dd, yyyy = s[:2], s[2:4], s[4:]
    year, month, day = int(yyyy), int(mm), int(dd)
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    if not (YEAR_MIN - 5 <= year <= YEAR_MAX + 2):  # sanity band, wider than our window
        return ""
    return f"{yyyy}-{mm}-{dd}"


# ------------------------------------------------------------------ party lookups


def load_party_lookups() -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    """cand_id -> (party, office) from cn*, cmte_id -> (party, committee type) from cm*."""
    cand: dict[str, tuple[str, str]] = {}
    cmte: dict[str, tuple[str, str]] = {}
    linked: dict[str, str] = {}
    for cycle in CYCLES:
        yy = f"{cycle % 100:02d}"
        for r in rows_of(f"cn{yy}", CN_COLS):
            cid = r["cand_id"].strip()
            party = PARTY_ALIAS.get(r["cand_pty_affiliation"].strip().upper(),
                                    r["cand_pty_affiliation"].strip().upper())
            if cid and (cid not in cand or party):
                cand[cid] = (party, r["cand_office"].strip().upper())
        for r in rows_of(f"cm{yy}", CM_COLS):
            cid = r["cmte_id"].strip()
            party = PARTY_ALIAS.get(r["cmte_pty_affiliation"].strip().upper(),
                                    r["cmte_pty_affiliation"].strip().upper())
            if cid and (cid not in cmte or party):
                cmte[cid] = (party, r["cmte_tp"].strip().upper())
            # a leadership/authorized committee usually leaves cmte_pty_affiliation blank
            # but names its candidate - borrow that candidate's party
            if cid and not cmte[cid][0] and r["cand_id"].strip():
                linked.setdefault(cid, r["cand_id"].strip())
    filled = 0
    for cid, cand_id in linked.items():
        party, ctype = cmte[cid]
        if not party and cand.get(cand_id, ("", ""))[0]:
            cmte[cid] = (cand[cand_id][0], ctype)
            filled += 1
    print(f"party lookups: {len(cand)} candidates, {len(cmte)} committees "
          f"({filled} committee parties filled in from their linked candidate)")
    return cand, cmte


# --------------------------------------------------------------- transaction parse


def parse_transactions(committee_ids: set[str]) -> list[dict]:
    """Every itemized transaction filed BY one of our matched corporate PACs."""
    cand_party, cmte_party = load_party_lookups()
    seen: set[str] = set()
    out: list[dict] = []
    bad_dates = 0
    for cycle in CYCLES:
        yy = f"{cycle % 100:02d}"
        for stem, cols in ((f"pas2{yy}", PAS2_COLS), (f"oth{yy}", OTH_COLS)):
            kept = scanned = 0
            for r in rows_of(stem, cols):
                scanned += 1
                cid = r["cmte_id"].strip()
                if cid not in committee_ids:
                    continue
                sub = r["sub_id"].strip()
                # the same transaction is republished in several two-year files
                if sub and sub in seen:
                    continue
                if sub:
                    seen.add(sub)
                date = parse_date(r["transaction_dt"])
                if not date:
                    bad_dates += 1
                try:
                    amount = float(r["transaction_amt"])
                except ValueError:
                    continue
                other = r["other_id"].strip()
                cand_id = r.get("cand_id", "").strip()
                party, office = cand_party.get(cand_id, ("", ""))
                rec_party, rec_type = cmte_party.get(other, ("", ""))
                out.append({
                    "committee_id": cid,
                    "disbursement_date": date,
                    "disbursement_amount": amount,
                    "purpose_category": "",  # bulk files carry no purpose category
                    "disbursement_type": r["transaction_tp"].strip().upper(),
                    "recipient_committee_id": other,
                    "recipient_name": r["name"].strip(),
                    "recipient_party": party or rec_party,
                    "recipient_committee_type": rec_type,
                    "candidate_id": cand_id,
                    "candidate_office": office,
                    "memo_cd": r["memo_cd"].strip().upper(),
                    "sub_id": sub,
                    "bulk_file": f"{stem}.zip",
                })
                kept += 1
            print(f"  {stem}.zip: {scanned:>9,} rows scanned, {kept:>7,} kept", flush=True)
    print(f"{len(out):,} transactions from {len({r['committee_id'] for r in out})} committees; "
          f"{bad_dates} rows had an unparseable transaction date")
    return out


# The ten committees that ARE the sitting administration's party apparatus; kept by id in
# the compact file so admin_committee_usd stays exact. Mirrors political_alignment.py.
ADMIN_COMMITTEE_IDS = {
    "C00003418", "C00027466", "C00075820", "C00580100", "C00828541",  # REP
    "C00010603", "C00042366", "C00000935", "C00431445", "C00703975",  # DEM
}


def quarter_of(date: str) -> str:
    return f"{date[:4]}Q{(int(date[5:7]) - 1) // 3 + 1}" if len(date) == 10 else ""


def write_disbursements(rows: list[dict]) -> None:
    """Two files: the full transaction detail, and the compact roll-up the indicator reads.

    The detail file is ~46 MB, over the 20 MB the repo commits (AGENTS.md 4), so it is
    git-ignored and rebuilt from the cached zips in ~2 minutes. The compact file keeps
    every field the indicator actually groups on - filer, quarter, transaction type,
    recipient party, and the recipient id when it is one of the administration's own
    committees - so the panel is byte-for-byte reproducible from what IS committed.
    """
    detail_cols = [
        "committee_id", "disbursement_date", "disbursement_amount", "purpose_category",
        "disbursement_type", "recipient_committee_id", "recipient_name",
        "recipient_party", "recipient_committee_type", "candidate_id",
        "candidate_office", "memo_cd", "sub_id", "bulk_file",
    ]
    rows = sorted(rows, key=lambda r: (r["committee_id"], r["disbursement_date"], r["sub_id"]))
    with TX_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, detail_cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    years = sorted({r["disbursement_date"][:4] for r in rows if r["disbursement_date"]})
    print(f"wrote {TX_CSV.relative_to(ROOT).as_posix()}: {len(rows):,} transactions, "
          f"{len({r['committee_id'] for r in rows})} committees, years {years[0]}-{years[-1]}"
          " (git-ignored, see .gitignore)")

    # memo_cd 'X' is a breakdown of a transaction itemized elsewhere in the same file -
    # summing both double-counts the money, so it never enters the roll-up.
    agg: dict[tuple, list] = {}
    memo = 0
    for r in rows:
        if r["memo_cd"] == "X":
            memo += 1
            continue
        q = quarter_of(r["disbursement_date"])
        rid = r["recipient_committee_id"]
        key = (r["committee_id"], q, r["disbursement_type"], r["recipient_party"],
               rid if rid in ADMIN_COMMITTEE_IDS else "")
        cell = agg.setdefault(key, [0.0, 0])
        cell[0] += r["disbursement_amount"]
        cell[1] += 1
    cols = ["committee_id", "quarter", "disbursement_type", "recipient_party",
            "admin_committee_id", "amount_usd", "n_transactions"]
    with DISB_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(cols)
        for key in sorted(agg):
            w.writerow(list(key) + [round(agg[key][0], 2), agg[key][1]])
    print(f"wrote {DISB_CSV.relative_to(ROOT).as_posix()}: {len(agg):,} committee-quarter-type "
          f"rows (dropped {memo} memo entries, memo_cd=X)")


# ------------------------------------------------------------------------ coverage


def master_names_by_cycle() -> dict[int, dict[str, set[str]]]:
    """Per cycle: core name of every sponsoring organisation / committee -> committee ids.

    A corporate PAC (an SSF) must name its connected organisation when it registers, so
    this is the FEC's own answer to "does company X sponsor a committee in this cycle?".
    Used only to decide whether a zero is real - never to create a company-committee link.
    """
    per_cycle: dict[int, dict[str, set[str]]] = {}
    for cycle in CYCLES:
        yy = f"{cycle % 100:02d}"
        index: dict[str, set[str]] = {}
        for r in rows_of(f"cm{yy}", CM_COLS):
            for field in (r["connected_org_nm"], r["cmte_nm"]):
                core = core_name(field or "")
                if core:
                    index.setdefault(core, set()).add(r["cmte_id"].strip())
        per_cycle[cycle] = index
        print(f"  cm{yy}.zip: {len(index)} distinct sponsor / committee core names")
    return per_cycle


def committees_named_like(company_names: list[dict], index: dict[str, set[str]]) -> set[str]:
    """Committee ids in one cycle whose sponsor or own name starts with the company name."""
    hits: set[str] = set()
    for alias in company_names:
        core = core_name(alias["name"])
        if not core:
            continue
        for name, ids in index.items():
            if name == core or name.startswith(core + " "):
                hits |= ids
    return hits


def write_coverage(rows: list[dict], universe_fallback: Path | None) -> None:
    """One row per S&P 500 company saying WHY it has (or has not) political-money data.

    Three states, and the difference matters (AGENTS.md 4.6):
      downloaded  this company's PAC transactions were actually read out of the bulk
                  files. A quarter with no transaction is a REAL zero.
      no_pac      the company is not the sponsoring organisation of ANY committee in the
                  FEC committee master, in any cycle. It genuinely spends no PAC money,
                  so a zero is real.
      unresolved  we could not link the company to a committee, but a committee whose
                  name or sponsor starts with the company's name does exist. Could be
                  the company's PAC under a name our rules miss, could be an unrelated
                  firm. No evidence either way -> NO ROW in the panel, never a zero.

    `unresolved_cycles` catches the same mistake one cycle at a time: a company whose
    matched PAC stopped filing while a NEW same-named committee appeared is not spending
    zero, we are simply pointed at the dead committee. Those cycles are dropped too. A
    matched PAC that terminates with no successor in the master IS a real zero and stays.
    """
    companies = load_company_list(universe_fallback)
    aliases = load_aliases()
    with MATCHES_CSV.open(encoding="utf-8") as f:
        matches = list(csv.DictReader(f))
    # a committee can belong to two tickers of ONE company (FOX/FOXA, GOOG/GOOGL share a
    # CIK) - so this is one-to-many in both directions and must never be a plain dict
    per_ticker_cmte: dict[str, set[str]] = defaultdict(set)
    cmte_to_tickers: dict[str, set[str]] = defaultdict(set)
    for r in matches:
        per_ticker_cmte[r["ticker"]].add(r["committee_id"])
        cmte_to_tickers[r["committee_id"]].add(r["ticker"])

    n_tx: dict[str, int] = defaultdict(int)
    for r in rows:
        for t in cmte_to_tickers[r["committee_id"]]:
            n_tx[t] += 1

    per_cycle = master_names_by_cycle()
    out = []
    for comp in companies:
        ticker = comp["ticker"].strip().upper()
        cmtes = sorted(per_ticker_cmte.get(ticker, ()))
        names = aliases.get(ticker) or [{"name": comp.get("name", "")}]
        hits_by_cycle = {cy: committees_named_like(names, per_cycle[cy]) for cy in CYCLES}
        if cmtes:
            # cycles where our committees are all gone but a same-named one is registered
            gaps = [cy for cy in CYCLES if hits_by_cycle[cy] and not (hits_by_cycle[cy] & set(cmtes))]
            status = "downloaded"
            evidence = f"{len(cmtes)} matched committee(s), {n_tx[ticker]} transactions"
            if gaps:
                evidence += (f"; no matched committee registered in cycle(s) "
                             f"{'/'.join(str(c) for c in gaps)} while another same-named "
                             f"committee is - those years are dropped")
        else:
            gaps = []
            all_hits = sorted({c for cy in CYCLES for c in hits_by_cycle[cy]})
            if all_hits:
                status = "unresolved"
                named = sorted({n for cy in CYCLES for n, ids in per_cycle[cy].items()
                                if ids & set(all_hits)})
                evidence = "FEC committee master has: " + "; ".join(named[:3])
            else:
                status = "no_pac"
                evidence = "no committee in the FEC committee master names this company as sponsor"
        out.append({
            "ticker": ticker,
            "data_status": status,
            "n_committees": len(cmtes),
            "committee_ids": "|".join(cmtes),
            "n_transactions": n_tx.get(ticker, 0),
            "unresolved_cycles": "|".join(str(c) for c in gaps),
            "evidence": evidence,
        })
    with COVERAGE_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, ["ticker", "data_status", "n_committees", "committee_ids",
                               "n_transactions", "unresolved_cycles", "evidence"],
                           lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: r["ticker"]))
    counts = defaultdict(int)
    for r in out:
        counts[r["data_status"]] += 1
    print(f"wrote {COVERAGE_CSV.relative_to(ROOT).as_posix()}: {len(out)} companies")
    for k in ("downloaded", "no_pac", "unresolved"):
        print(f"  {k:11} {counts[k]}")
    gapped = [r for r in out if r["unresolved_cycles"]]
    print(f"  {len(gapped)} downloaded companies have cycle gaps that are dropped:")
    for r in gapped:
        print(f"    {r['ticker']:6} cycles {r['unresolved_cycles']}")


# ---------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--parse-only", action="store_true", help="skip downloading")
    ap.add_argument("--universe", type=Path, default=None, help="fallback company list CSV")
    args = ap.parse_args()

    if not args.parse_only:
        download_all()
    with MATCHES_CSV.open(encoding="utf-8") as f:
        committee_ids = {r["committee_id"] for r in csv.DictReader(f)}
    print(f"{len(committee_ids)} matched corporate PAC committees to filter for")
    rows = parse_transactions(committee_ids)
    write_disbursements(rows)
    write_coverage(rows, args.universe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
