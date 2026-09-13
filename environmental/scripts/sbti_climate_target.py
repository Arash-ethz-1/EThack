"""sbti_climate_target - ambition and credibility of a company's validated climate target.

What it measures: where a company stands on the Science Based Targets initiative (SBTi)
Target Dashboard - the public register of corporate emission-reduction targets that
SBTi has checked against climate science. Ordinal value, higher is better:

  4 = net-zero target validated          (net_zero_status = "Targets set")
  3 = near-term target set, 1.5C         (near_term_status = "Targets set", classification 1.5C)
  2 = near-term target set, well-below 2C or 2C
  1 = committed only                     (near_term or net_zero status = "Committed")
  0 = not on the dashboard, or "Commitment removed"

A classification listing several targets ("1.5C/Well-below 2C") counts at its weakest
part: 3 only if every listed near-term target is 1.5C.
Several dashboard rows can map to one company (parent + subsidiaries): the highest wins.
A company with no row gets 0 with note "not listed on SBTi dashboard on <date>" - absence
from the register is the observation itself, so every universe company gets a row.
This measures targets, not actual emissions (see catalog).

Source: SBTi Target Dashboard companies file
  https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx
  (linked from https://sciencebasedtargets.org/target-dashboard)

Matching dashboard rows to universe tickers, most reliable first:
  1. isin - ISIN -> US ticker via OpenFIGI (POST https://api.openfigi.com/v3/mapping,
     idType ID_ISIN, exchCode US; no API key: 25 requests/min, 10 ISINs per request).
     OpenFIGI only accepts POST, which common.io.cached_download cannot send, so the
     responses are cached here in environmental/raw/openfigi/ and logged in
     environmental/raw/_downloads.csv in the same format.
  2. name - rows whose ISIN did not resolve to a universe ticker: the SBTi name,
     normalised with social/scripts/_company_match.normalise, equals the normalised
     universe name or a current/former SEC name (social/raw/aliases.csv), and that
     normalised name points to exactly one ticker. Names made only of generic words are
     not used. A name match is only accepted for a row located in the United States (or
     listed in NAME_MATCH_NON_US after a hand check), so a foreign company that shares a
     US company's name cannot match - e.g. "SQUARE" (France) is not Block Inc (formerly
     Square), and "Domino's Pizza Group plc" (UK franchisee) is not Domino's Pizza Inc.
  3. manual - MANUAL_MATCHES: rows checked by hand that no rule can match (renamed or
     merged companies whose ISIN is retired, a predecessor that is now the group itself).
  Deviation from docs/PLAN.md ("subsidiaries: take the highest"): a listed unit whose
  parent is not listed at all (SUBSIDIARY_ONLY) is NOT counted - its target covers the
  unit only. The parent keeps 0 and the note names the unit.
  Every match is written to environmental/raw/sbti_matches.csv for hand checks.
  MATCH_EXCLUDE lists rows found wrong by hand. Share classes of one company (same SEC
  CIK, e.g. GOOG/GOOGL) get the same value.

The dashboard is a snapshot of current status, so `year` = the year the file was
downloaded (from environmental/raw/_downloads.csv), not a reporting year.

The xlsx is read without a new dependency: it is a zip of XML files
(xl/sharedStrings.xml + xl/worksheets/sheet1.xml).

Owner:  Arash Bayat
Run:    python run.py build environmental sbti_climate_target
Output: environmental/indicators/sbti_climate_target.csv (docs/DATA_FORMAT.md)
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "social" / "scripts"))

from common.config import raw_dir  # noqa: E402
from common.io import cached_download, load_universe, write_indicator  # noqa: E402

CATEGORY = "environmental"
INDICATOR_ID = "sbti_climate_target"
SOURCE = "SBTi Target Dashboard"
XLSX_URL = "https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx"
XLSX_FILE = "sbti_companies.xlsx"
OPENFIGI_URL = "https://api.openfigi.com/v3/mapping"
OPENFIGI_BATCH = 10
OPENFIGI_PAUSE_S = 2.6  # 25 requests per minute without a key

# (sbti_id, ticker) pairs a hand check found to be wrong matches. Empty until one is found.
MATCH_EXCLUDE: set[tuple[str, str]] = set()
# sbti_ids of rows located outside the US whose exact name match was checked by hand.
# Their ISIN in the file is missing or retired (OpenFIGI: "No identifier found").
NAME_MATCH_NON_US = {
    "40001391",  # TE Connectivity Ltd, Switzerland, no ISIN            -> TEL
    "40001916",  # Amcor plc, Switzerland, JE00BJ1F3079                 -> AMCR
    "40005379",  # Aptiv PLC, Ireland, JE00B783TY65                     -> APTV
    "40006753",  # Seagate Technology, Ireland, IE00B58JVZ52            -> STX (SEC former name Seagate Technology plc)
    "40005184",  # Trane Technologies Plc., Ireland, US456873AF50       -> TT
}
# Rows no automatic rule can match, checked by hand: sbti_id -> (ticker, why).
MANUAL_MATCHES = {
    "40014590": ("PTC", "'PTC Inc.' - name too short for the automatic name rule"),
    "40012156": ("BG", "'Bunge Limited' became Bunge Global SA (redomiciled 2023); ISIN retired"),
    "40005053": ("J", "'Jacobs' = Jacobs Engineering Group, reorganised as Jacobs Solutions 2022; ISIN retired"),
    "40013210": ("PSKY", "'Paramount Global' is a subsidiary of Paramount Skydance since the 2025 merger"),
    "40000368": ("SW", "'Smurfit Kappa Group' merged into Smurfit Westrock plc 2024"),
    "40007037": ("SW", "'WestRock Company' merged into Smurfit Westrock plc 2024"),
}
# Listed units of a universe company whose parent is NOT listed itself, checked against the
# parent's 10-K Exhibit 21 (social/raw/subsidiaries.csv). Not counted: a unit's target
# covers that unit only, and would give the whole group the unit's score. The parent keeps
# 0 and the note names the unit, so a reader can see it.
SUBSIDIARY_ONLY = {
    "40010957": ("CPRT", "Copart UK Limited is in Copart's 10-K Exhibit 21"),
    "40006405": ("TXT", "Kautex entities are in Textron's 10-K Exhibit 21"),
}
# SEC former names older than this are skipped: the dashboard started in 2015, and an old
# name can belong to another company today (Moody's was once "Dun & Bradstreet Corp").
ALIAS_MIN_VALID_TO = "2015-01-01"

XML_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# ---------------------------------------------------------------- xlsx reading
def _col_index(ref: str) -> int:
    """'C12' -> 2"""
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(path: Path) -> pd.DataFrame:
    """First worksheet of an .xlsx as a DataFrame of strings (header = first row)."""
    with zipfile.ZipFile(path) as z:
        shared = [
            "".join(t.text or "" for t in si.iter(f"{XML_NS}t"))
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{XML_NS}si")
        ]
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in sheet.iter(f"{XML_NS}row"):
        row = {}
        for c in r.findall(f"{XML_NS}c"):
            kind, v = c.get("t"), c.find(f"{XML_NS}v")
            if kind == "inlineStr":
                value = "".join(t.text or "" for t in c.iter(f"{XML_NS}t"))
            elif v is None:
                continue
            elif kind == "s":
                value = shared[int(v.text)]
            else:
                value = v.text
            row[_col_index(c.get("r"))] = value
        rows.append(row)
    header = rows[0]
    width = max(header) + 1
    return pd.DataFrame(
        [[r.get(i, "") for i in range(width)] for r in rows[1:]],
        columns=[header.get(i, f"col{i}") for i in range(width)],
    )


def _ascii(text: object) -> str:
    """Company names can hold characters a Windows console cannot print."""
    return str(text).encode("ascii", "replace").decode()


def excel_date(serial: str) -> str:
    """Excel serial (days since 1899-12-30) -> 'YYYY-MM-DD'; '' if empty."""
    try:
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(float(serial)))).isoformat()
    except (TypeError, ValueError):
        return ""


def download_date(filename: str) -> str:
    """UTC date of the latest logged download of <filename> in raw/_downloads.csv."""
    log = pd.read_csv(raw_dir(CATEGORY) / "_downloads.csv", dtype=str)
    stamps = log.loc[log["file"] == filename, "retrieved_utc"]
    if stamps.empty:
        raise SystemExit(f"{filename} not in environmental/raw/_downloads.csv")
    return stamps.iloc[-1][:10]


# ---------------------------------------------------------------- value
def row_value(r: pd.Series) -> int | None:
    """Ordinal 0-4 for one dashboard row; None if a set target has no usable classification."""
    if r["net_zero_status"] == "Targets set":
        return 4
    if r["near_term_status"] == "Targets set":
        parts = [p.strip() for p in r["near_term_target_classification"].replace("°", "").split("/")]
        levels = []
        for p in parts:
            if p == "1.5C":
                levels.append(3)
            elif p in ("Well-below 2C", "2C"):
                levels.append(2)
            else:
                return None
        return min(levels)
    if "Committed" in (r["near_term_status"], r["net_zero_status"]):
        return 1
    return 0


# ---------------------------------------------------------------- ISIN -> ticker
def _log_download(filename: str, url: str, n_bytes: int) -> None:
    log = raw_dir(CATEGORY) / "_downloads.csv"
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with log.open("a", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerow([filename, url, stamp, n_bytes])


def openfigi_tickers(isins: list[str]) -> dict[str, set[str]]:
    """ISIN -> set of US tickers (dot notation). Each batch response cached in raw/openfigi/."""
    out: dict[str, set[str]] = {}
    folder = raw_dir(CATEGORY) / "openfigi"
    folder.mkdir(parents=True, exist_ok=True)
    isins = sorted(set(isins))
    for start in range(0, len(isins), OPENFIGI_BATCH):
        batch = isins[start : start + OPENFIGI_BATCH]
        key = hashlib.sha1(",".join(batch).encode()).hexdigest()[:16]
        filename = f"openfigi/{key}.json"
        path = raw_dir(CATEGORY) / filename
        if not path.exists():
            body = [{"idType": "ID_ISIN", "idValue": i, "exchCode": "US"} for i in batch]
            for attempt in range(6):
                resp = requests.post(OPENFIGI_URL, json=body, timeout=60)
                if resp.status_code == 429:
                    time.sleep(30)
                    continue
                resp.raise_for_status()
                break
            else:
                raise SystemExit("OpenFIGI kept answering 429 - try again later")
            path.write_text(json.dumps({"isins": batch, "response": resp.json()}), encoding="utf-8")
            _log_download(filename, OPENFIGI_URL, len(resp.content))
            time.sleep(OPENFIGI_PAUSE_S)
            print(f"  openfigi {start + len(batch)}/{len(isins)}", flush=True)
        cached = json.loads(path.read_text(encoding="utf-8"))
        for isin, result in zip(cached["isins"], cached["response"]):
            tickers = {d["ticker"].replace("/", ".").upper() for d in result.get("data", []) if d.get("ticker")}
            out[isin] = tickers
    return out


# ---------------------------------------------------------------- name fallback
def name_index() -> dict[str, str]:
    """normalised name -> ticker, only names that point to exactly one ticker."""
    from _company_match import normalise, usable  # read-only helper from social/

    universe = load_universe()
    pairs = [(normalise(n), t) for n, t in zip(universe["name"], universe["ticker"])]
    aliases = ROOT / "social" / "raw" / "aliases.csv"
    if aliases.exists():
        a = pd.read_csv(aliases, dtype=str)
        a = a[a["valid_to"].isna() | (a["valid_to"] >= ALIAS_MIN_VALID_TO)]
        pairs += [(normalise(n), t) for n, t in zip(a["name"], a["ticker"])]
    by_name: dict[str, set[str]] = {}
    for norm, t in pairs:
        if usable(norm):
            by_name.setdefault(norm, set()).add(t)
    return {n: next(iter(ts)) for n, ts in by_name.items() if len(ts) == 1}


def match_rows(sbti: pd.DataFrame, universe_tickers: set[str]) -> pd.DataFrame:
    """-> DataFrame(sbti row index, ticker, match) for rows that map to a universe ticker."""
    from _company_match import normalise

    isin_map = openfigi_tickers([i for i in sbti["isin"] if len(i) == 12])
    names = name_index()
    out = []
    for idx, r in sbti.iterrows():
        if r["sbti_id"] in MANUAL_MATCHES:
            out.append((idx, MANUAL_MATCHES[r["sbti_id"]][0], "manual"))
            continue
        tickers = isin_map.get(r["isin"], set()) & universe_tickers
        if len(tickers) == 1:
            out.append((idx, next(iter(tickers)), "isin"))
            continue
        if len(tickers) > 1:
            print(f"  WARN isin {r['isin']} ({_ascii(r['company_name'])}) -> several universe tickers {sorted(tickers)}, skipped")
            continue
        if not r["location"].startswith("United States") and r["sbti_id"] not in NAME_MATCH_NON_US:
            continue
        t = names.get(normalise(r["company_name"]))
        if t:
            out.append((idx, t, "name"))
    m = pd.DataFrame(out, columns=["row", "ticker", "match"])
    keep = [(sbti.at[i, "sbti_id"], t) not in MATCH_EXCLUDE for i, t in zip(m["row"], m["ticker"])]
    return m[keep]


# ---------------------------------------------------------------- build
def build() -> pd.DataFrame:
    universe = load_universe()
    xlsx = cached_download(XLSX_URL, CATEGORY, XLSX_FILE)
    snapshot = download_date(XLSX_FILE)
    year = int(snapshot[:4])

    sbti = read_xlsx(xlsx).fillna("")
    for c in sbti.columns:
        sbti[c] = sbti[c].astype(str).str.strip()
    sbti["sbti_id"] = sbti["sbti_id"].map(lambda s: str(int(float(s))) if s else "")
    sbti["value"] = sbti.apply(row_value, axis=1)
    print(f"SBTi file: {len(sbti)} rows, downloaded {snapshot}")

    m = match_rows(sbti, set(universe["ticker"]))
    names = dict(zip(universe["ticker"], universe["name"]))
    ciks = dict(zip(universe["ticker"], universe["cik"]))
    log = m.join(sbti, on="row")
    log["cik"] = log["ticker"].map(ciks)
    log["universe_name"] = log["ticker"].map(names)
    log[["ticker", "universe_name", "match", "sbti_id", "company_name", "isin", "location",
         "near_term_status", "near_term_target_classification", "net_zero_status", "value"]].sort_values(
        ["ticker", "value"]).to_csv(raw_dir(CATEGORY) / "sbti_matches.csv", index=False, lineterminator="\n")
    print(f"matched rows: {len(m)} ({(m['match'] == 'isin').sum()} isin, {(m['match'] == 'name').sum()} name, "
          f"{(m['match'] == 'manual').sum()} manual), "
          f"{m['ticker'].nunique()} tickers")

    unclassified = log[log["value"].isna()]
    for _, r in unclassified.iterrows():
        print(f"  WARN {r['ticker']}: '{_ascii(r['company_name'])}' target set but classification "
              f"'{r['near_term_target_classification']}' unknown - row ignored")
    log = log.dropna(subset=["value"])

    rows = []
    for ticker, cik in zip(universe["ticker"], universe["cik"]):
        mine = log[log["cik"] == cik]  # share classes (GOOG/GOOGL) are one company
        if len(mine) == 0:
            if cik in set(unclassified["cik"]):
                continue  # on the dashboard, but no usable value: a gap, not a 0
            note = f"not listed on SBTi dashboard on {snapshot}"
            for sid, (sub_ticker, why) in SUBSIDIARY_ONLY.items():
                if sub_ticker == ticker:
                    sub = sbti[sbti["sbti_id"] == sid].iloc[0]
                    note += (f"; its unit '{sub['company_name']}' is listed (near_term={sub['near_term_status']}, "
                             f"net_zero={sub['net_zero_status'] or '-'}) but not counted - unit target only; {why}")
            rows.append({"ticker": ticker, "year": year, "value": 0, "note": note})
            continue
        best = mine.sort_values("value", ascending=False, kind="stable").iloc[0]
        note = (
            f"SBTi '{best['company_name']}' (sbti_id {best['sbti_id']}, matched by {best['match']}): "
            f"near_term={best['near_term_status'] or '-'} {best['near_term_target_classification']}".rstrip()
            + f"; net_zero={best['net_zero_status'] or '-'}; date_updated {excel_date(best['date_updated'])}"
        )
        if best["match"] == "manual":
            note += f"; manual match: {MANUAL_MATCHES[best['sbti_id']][1]}"
        if best["ticker"] != ticker:
            note += f"; matched to share class {best['ticker']} (same SEC CIK)"
        if len(mine) > 1:
            note += f"; highest of {len(mine)} dashboard rows"
        rows.append({"ticker": ticker, "year": year, "value": int(best["value"]), "note": note})

    df = pd.DataFrame(rows)
    df["source"] = SOURCE
    df["source_url"] = XLSX_URL
    df["retrieved"] = snapshot  # the day the dashboard file was downloaded
    print("value counts:", df["value"].value_counts().sort_index().to_dict())
    return df


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
