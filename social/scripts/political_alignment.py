"""political_alignment - how much political money a company spends per dollar of revenue.

What it measures: the money a company's own corporate PAC contributes to federal
candidates and political committees, per $M of revenue, quarter by quarter,
2016Q1-2025Q4. Buying access to legislators is influence-seeking rather than
impact-creating, so LOWER IS BETTER (`higher_is_better = false` in the catalog).

Source: FEC bulk transaction files (no API key needed) - https://www.fec.gov/data/browse-data/?tab=bulk-data
  pas2{YY}.zip  contributions from committees to candidates
  oth{YY}.zip   any transaction from one committee to another
  cm{YY}.zip / cn{YY}.zip   committee / candidate master, for the recipient's party
The corporate PACs themselves were identified once through the OpenFEC API
(social/scripts/_fec_download.py match -> social/raw/fec_pac_matches.csv).
Revenue denominator: universe/financials.csv (shared, 2019-2025), filled back to 2016
from social/raw/financials.csv - same SEC XBRL frames method.

THREE DATA STATES, never mixed up (AGENTS.md 4.6 - a missing company is a missing row):
  downloaded  the company's PAC transactions were actually read out of the bulk files.
              A quarter with no contribution is a REAL zero.
  no_pac      no committee in the FEC committee master, in any cycle 2016-2026, names
              this company as its sponsoring organisation. It genuinely spends no
              federal PAC money, so zero is a REAL zero (Tesla and Agilent are examples
              we checked by hand against the raw cm files).
  unresolved  we could not link the company to a committee, but a committee named after
              it does exist in the master file. NO ROW - we do not know the number, and
              writing 0 would let those companies rank as perfectly clean for free.

Run:    python social/scripts/_fec_download.py committees   # once, API, for the matching
        python social/scripts/_fec_download.py match        # once -> fec_pac_matches.csv
        python social/scripts/_fec_bulk.py                  # bulk download + parse, ~15 min
        python run.py build social political_alignment

Output:
  social/indicators/political_alignment.csv   ticker, year, value (shared format, annual)
  social/raw/political_alignment_panel.csv    the full QUARTERLY panel, with data_status
                                              and the extra partisan-skew and
                                              administration columns (the shared format
                                              has no quarter column yet, so the panel
                                              lives in raw/)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.config import ROOT, raw_dir  # noqa: E402
from common.io import today_utc, write_indicator  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "political_alignment"
SOURCE = "FEC bulk files (pas2/oth transactions, corporate PACs)"
SOURCE_URL = "https://www.fec.gov/data/browse-data/?tab=bulk-data"

RAW = raw_dir(CATEGORY)
MATCHES_CSV = RAW / "fec_pac_matches.csv"
DISB_CSV = RAW / "fec_pac_disbursements.csv"
COVERAGE_CSV = RAW / "fec_pac_coverage.csv"
# universe/financials.csv is the team's shared denominator (owner: Arash) and wins where
# it has data. It starts at 2019, so social/raw/financials.csv - same SEC XBRL frames
# method - fills 2016-2018 to keep the full 10-year window.
FINANCIALS_SHARED = ROOT / "universe" / "financials.csv"
FINANCIALS_LOCAL = RAW / "financials.csv"
PANEL_CSV = RAW / "political_alignment_panel.csv"

QUARTERS = [f"{y}Q{q}" for y in range(2016, 2026) for q in (1, 2, 3, 4)]

# Which party held the White House in each quarter. A president is sworn in on 20 January,
# so the new administration owns ~80% of the first quarter of an inauguration year.
ADMIN_PARTY = {}
for _q in QUARTERS:
    _y = int(_q[:4])
    ADMIN_PARTY[_q] = "DEM" if _y <= 2016 or 2021 <= _y <= 2024 else "REP"

# "Committees affiliated with the sitting administration": the three national committees
# of the president's party plus his own principal campaign committee(s). Verified against
# /v1/committee/<id>/ - see the check printed by main().
ADMIN_COMMITTEES = {
    "REP": {
        "C00003418",  # Republican National Committee
        "C00027466",  # NRSC
        "C00075820",  # NRCC
        "C00580100",  # Donald J. Trump for President, Inc. (2016, 2020)
        "C00828541",  # Donald J. Trump for President 2024, Inc.
    },
    "DEM": {
        "C00010603",  # Democratic National Committee
        "C00042366",  # DSCC
        "C00000935",  # DCCC
        "C00431445",  # Obama for America
        "C00703975",  # Biden for President
    },
}


def quarter_of(date: pd.Series) -> pd.Series:
    d = pd.to_datetime(date, errors="coerce")
    return d.dt.year.astype("Int64").astype(str) + "Q" + d.dt.quarter.astype("Int64").astype(str)


def load_matches() -> pd.DataFrame:
    if not MATCHES_CSV.exists():
        raise FileNotFoundError(
            f"{MATCHES_CSV} missing - run: python social/scripts/_fec_download.py match"
        )
    return pd.read_csv(MATCHES_CSV, dtype=str)


def load_disbursements() -> pd.DataFrame:
    """The compact roll-up written by _fec_bulk.py: filer x quarter x type x party.

    Memo entries (memo_cd=X, a breakdown of a transaction itemized elsewhere) are already
    excluded there, so nothing here is double-counted.
    """
    if not DISB_CSV.exists():
        raise FileNotFoundError(
            f"{DISB_CSV} missing - run: python social/scripts/_fec_bulk.py"
        )
    df = pd.read_csv(
        DISB_CSV,
        dtype={"committee_id": str, "admin_committee_id": str, "recipient_party": str},
    )
    df["amount_usd"] = pd.to_numeric(df["amount_usd"], errors="coerce")
    df["n_transactions"] = pd.to_numeric(df["n_transactions"], errors="coerce").fillna(0).astype(int)
    print(f"disbursements: {len(df)} committee-quarter-type rows, "
          f"{df['committee_id'].nunique()} committees")
    return df[df["quarter"].isin(QUARTERS)].copy()


def load_coverage() -> pd.DataFrame:
    """Per ticker: downloaded / no_pac / unresolved. See the module docstring."""
    if not COVERAGE_CSV.exists():
        raise FileNotFoundError(
            f"{COVERAGE_CSV} missing - run: python social/scripts/_fec_bulk.py"
        )
    cov = pd.read_csv(COVERAGE_CSV, dtype=str)
    cov["n_pac_committees"] = pd.to_numeric(cov["n_committees"], errors="coerce").fillna(0).astype(int)
    cov["unresolved_cycles"] = cov["unresolved_cycles"].fillna("")
    counts = cov["data_status"].value_counts().to_dict()
    print("coverage: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    return cov[["ticker", "data_status", "n_pac_committees", "unresolved_cycles"]]


def _read_revenue(path: Path) -> pd.DataFrame:
    """Annual revenue rows only; the quarterly rows in financials.csv are patchier."""
    if not path.exists():
        return pd.DataFrame(columns=["ticker", "year", "revenue_usd"])
    fin = pd.read_csv(path)
    if "quarter" in fin.columns:
        fin = fin[fin["quarter"].isna()]
    fin = fin[fin["revenue_usd"].notna()]
    fin = fin[["ticker", "year", "revenue_usd"]].copy()
    fin["ticker"] = fin["ticker"].str.strip().str.upper()
    fin["year"] = fin["year"].astype(int)
    fin["revenue_usd"] = pd.to_numeric(fin["revenue_usd"], errors="coerce")
    fin = fin[fin["revenue_usd"] > 0]
    return fin.drop_duplicates(["ticker", "year"])


def load_revenue() -> pd.DataFrame:
    """(ticker, year) -> annual revenue USD. Shared file wins; local fills earlier years."""
    shared = _read_revenue(FINANCIALS_SHARED)
    local = _read_revenue(FINANCIALS_LOCAL)
    both = pd.concat([local, shared])  # shared last -> its row wins the drop_duplicates
    rev = both.drop_duplicates(["ticker", "year"], keep="last").reset_index(drop=True)
    if rev.empty:
        raise SystemExit(
            "no revenue denominator found - need universe/financials.csv (Arash) or run "
            "social/scripts/_financials.py.\nAGENTS.md section 4 requires size-neutral values."
        )
    print(f"revenue: {len(shared)} rows from universe/financials.csv, "
          f"{len(rev) - len(shared)} additional from social/raw/financials.csv")
    return rev


# FEC transaction types that mean "this PAC gave money to a candidate or committee":
# 24K direct contribution, 24Z in-kind, 24E independent expenditure for, 24C coordinated
# party expenditure, 24F communication cost for, 24R electioneering communication.
# Everything else in the bulk files is a receipt (15*, 18*), a refund (22*) or a transfer
# to the PAC's own affiliate (24G) - not money handed to a politician.
CONTRIBUTION_TYPES = {"24K", "24Z", "24E", "24C", "24F", "24R"}


def is_contribution(df: pd.DataFrame) -> pd.Series:
    """Money given to candidates/committees, as opposed to transfers, refunds, receipts."""
    return df["disbursement_type"].fillna("").str.upper().isin(CONTRIBUTION_TYPES)


def build_panel() -> pd.DataFrame:
    """One row per company per quarter - but only for companies we can honestly fill in.

    A (ticker, quarter) row exists only when we know the number:
      * data_status "downloaded": the company's committees were read out of the bulk
        files, so a quarter with no contribution is a real 0.
      * data_status "no_pac": the company sponsors no committee at all, so 0 is real.
    Companies with data_status "unresolved" get NO rows. Writing 0 for them would make
    them rank as the cleanest companies in the index purely because we never found their
    money - exactly what AGENTS.md 4.6 forbids.
    """
    matches = load_matches()
    coverage = load_coverage()
    disb = load_disbursements()
    rev = load_revenue()

    # One committee can belong to two tickers of the SAME company (FOX/FOXA and NWS/NWSA
    # share a CIK), so this is a one-to-many join, not a lookup - a dict would silently
    # give the money to whichever ticker happened to be written last.
    link = matches[["committee_id", "ticker"]].drop_duplicates()
    disb = disb.merge(link, on="committee_id", how="inner")

    contrib = disb[is_contribution(disb)].copy()
    party = contrib["recipient_party"].fillna("").str.upper()
    contrib["rep_usd"] = contrib["amount_usd"].where(party.eq("REP"), 0.0)
    contrib["dem_usd"] = contrib["amount_usd"].where(party.eq("DEM"), 0.0)
    contrib["admin_party"] = contrib["quarter"].map(ADMIN_PARTY)
    contrib["admin_party_usd"] = contrib["amount_usd"].where(party.eq(contrib["admin_party"]), 0.0)
    in_admin_cmte = [
        cid in ADMIN_COMMITTEES.get(ap, set())
        for cid, ap in zip(contrib["admin_committee_id"].fillna(""), contrib["admin_party"])
    ]
    contrib["admin_committee_usd"] = contrib["amount_usd"].where(in_admin_cmte, 0.0)

    agg_c = contrib.groupby(["ticker", "quarter"]).agg(
        pac_contributions_usd=("amount_usd", "sum"),
        n_contributions=("n_transactions", "sum"),
        rep_usd=("rep_usd", "sum"),
        dem_usd=("dem_usd", "sum"),
        admin_party_usd=("admin_party_usd", "sum"),
        admin_committee_usd=("admin_committee_usd", "sum"),
    )
    # every outbound and inbound inter-committee transaction, contributions included -
    # the bulk files carry no operating expenses, so this is NOT the PAC's total spending
    agg_d = disb.groupby(["ticker", "quarter"]).agg(pac_transactions_usd=("amount_usd", "sum"))

    known = coverage[coverage["data_status"].isin(["downloaded", "no_pac"])]
    tickers = sorted(known["ticker"].unique())
    panel = pd.MultiIndex.from_product([tickers, QUARTERS], names=["ticker", "quarter"]).to_frame(
        index=False
    )
    # Drop the cycles where a company's matched PAC had stopped filing while a new
    # same-named committee was registered: those quarters are unknown, not zero.
    drop = {
        (r.ticker, int(c))
        for r in known.itertuples()
        for c in str(r.unresolved_cycles).split("|")
        if c
    }
    if drop:
        cycle = panel["quarter"].str[:4].astype(int).add(1).floordiv(2).mul(2)  # 2019 -> 2020
        keep = ~pd.Series(list(zip(panel["ticker"], cycle)), index=panel.index).isin(drop)
        print(f"dropped {(~keep).sum()} quarters from {len(drop)} ticker-cycles with a "
              f"registered but unmatched successor committee")
        panel = panel[keep].reset_index(drop=True)
    panel = panel.merge(agg_c, on=["ticker", "quarter"], how="left")
    panel = panel.merge(agg_d, on=["ticker", "quarter"], how="left")
    money_cols = [
        "pac_contributions_usd", "pac_transactions_usd", "rep_usd", "dem_usd",
        "admin_party_usd", "admin_committee_usd", "n_contributions",
    ]
    # every ticker left in the panel was either downloaded or has no PAC, so a hole here
    # is a measured zero, not a missing observation
    panel[money_cols] = panel[money_cols].fillna(0.0)
    panel = panel.merge(known[["ticker", "data_status", "n_pac_committees"]], on="ticker", how="left")

    panel["year"] = panel["quarter"].str[:4].astype(int)
    panel = panel.merge(rev, on=["ticker", "year"], how="left")

    # the score: political dollars per $M of that year's revenue, in this quarter
    panel["value"] = panel["pac_contributions_usd"] / (panel["revenue_usd"] / 1e6)
    panel.loc[panel["revenue_usd"].isna() | (panel["revenue_usd"] <= 0), "value"] = pd.NA

    two_party = panel["rep_usd"] + panel["dem_usd"]
    panel["partisan_skew"] = (panel["rep_usd"] - panel["dem_usd"]) / two_party.where(two_party > 0)
    panel["admin_party"] = panel["quarter"].map(ADMIN_PARTY)
    panel["admin_party_share"] = panel["admin_party_usd"] / panel["pac_contributions_usd"].where(
        panel["pac_contributions_usd"] > 0
    )

    # how the PAC was linked to the company: "exact" = FEC's own sponsoring-organisation
    # name equals the company's SEC name; "rule" = a looser rule, hand-checked once;
    # "no_pac" = there is nothing to link, the company sponsors no committee.
    conf = (
        matches.assign(exact=matches["match_rule"].eq("affiliated_exact"))
        .groupby("ticker")["exact"].all()
        .map({True: "exact", False: "rule"})
        .rename("match_confidence")
    )
    panel = panel.merge(conf, on="ticker", how="left")
    panel["match_confidence"] = panel["match_confidence"].fillna("no_pac")
    panel["source"] = SOURCE
    panel["source_url"] = SOURCE_URL
    panel["retrieved"] = today_utc()

    cols = [
        "ticker", "quarter", "year", "value", "data_status", "pac_contributions_usd",
        "pac_transactions_usd", "revenue_usd", "n_contributions", "n_pac_committees",
        "match_confidence", "rep_usd", "dem_usd", "partisan_skew", "admin_party",
        "admin_party_usd", "admin_party_share", "admin_committee_usd",
        "source", "source_url", "retrieved",
    ]
    return panel[cols].sort_values(["ticker", "quarter"]).reset_index(drop=True)


def build() -> pd.DataFrame:
    """Annual indicator rows in the shared format; also dumps the quarterly panel."""
    panel = build_panel()
    PANEL_CSV.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(PANEL_CSV, index=False, lineterminator="\n")
    by_status = panel.drop_duplicates("ticker")["data_status"].value_counts().to_dict()
    print(
        f"wrote {PANEL_CSV.relative_to(ROOT).as_posix()}: {len(panel)} rows, "
        f"{panel['ticker'].nunique()} tickers x {panel['quarter'].nunique()} quarters "
        f"({by_status})"
    )

    year = panel.groupby(["ticker", "year", "data_status"], as_index=False).agg(
        pac_contributions_usd=("pac_contributions_usd", "sum"),
        revenue_usd=("revenue_usd", "max"),
        n_contributions=("n_contributions", "sum"),
        n_pac_committees=("n_pac_committees", "max"),
    )
    year = year[year["revenue_usd"].notna() & (year["revenue_usd"] > 0)].copy()
    year["value"] = year["pac_contributions_usd"] / (year["revenue_usd"] / 1e6)
    year["source"] = SOURCE
    year["source_url"] = SOURCE_URL
    year["retrieved"] = today_utc()
    # the note carries the data state, so a reader can tell a measured zero from a
    # company that simply has no PAC - and neither is ever a guess
    measured = (
        "corporate PAC contributions to federal candidates/committees, USD per $M annual "
        "revenue; " + year["n_contributions"].astype(int).astype(str)
        + " contributions from " + year["n_pac_committees"].astype(int).astype(str)
        + " PAC(s)"
    )
    no_pac = (
        "no corporate PAC: the company sponsors no committee in the FEC committee master "
        "2016-2026, so its federal PAC spending is a measured 0"
    )
    year["note"] = measured.where(year["data_status"].eq("downloaded"), no_pac)
    return year[["ticker", "year", "value", "source", "source_url", "retrieved", "note"]]


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
