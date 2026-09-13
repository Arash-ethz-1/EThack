"""epa_penalty_intensity - US environmental penalties per $bn of revenue, trailing 5 years.

What it measures: how much a company paid in penalties for breaking US environmental law
(Clean Air Act, Clean Water Act, RCRA hazardous waste, CERCLA, TSCA, FIFRA, EPCRA, SDWA)
in the 5 years up to `year`, relative to its size. Every federal EPA civil enforcement case
that ended in a settlement or order is in EPA's ICIS-FE&C database, with the defendants and
the assessed federal and state/local penalty. Lower is better: a penalty is an official
finding that the company harmed or endangered the environment, not a self-reported claim.

How:
  1. EPA ECHO bulk case file (case_downloads.zip, cached in environmental/raw/epa_echo/):
     CASE_ENFORCEMENT_CONCLUSIONS -> per case: FED_PENALTY_ASSESSED_AMT +
     STATE_LOCAL_PENALTY_AMT, dated by SETTLEMENT_ENTERED_DATE (else lodged date, else
     SETTLEMENT_FY). CASE_DEFENDANTS -> the defendants named in the settlement.
  2. Defendant names are matched to S&P 500 parents with social/scripts/_company_match.py
     (exact normalised parent name, former SEC names, or a 10-K Exhibit 21 subsidiary) -
     the same reviewed matcher as workplace_injury_rate. A case's penalty is split equally
     across its distinct defendants; the matched share goes to the parent.
  3. value = sum of matched penalties with a settlement date in [year-4, year] / mean annual
     revenue over those years (SEC XBRL, environmental/scripts/_revenue.py) in $bn -> USD per $bn.
  4. A company with revenue but no matched case gets 0, with the note saying so. That is an
     observation (no federal EPA civil penalty found under its name or its subsidiaries'),
     not a guess - but a subsidiary missing from Exhibit 21 would be missed, so 0 means
     "none found", see environmental/raw/epa_penalty_matches.csv for every match.

Limits: federal EPA cases only (state-agency-only cases and criminal cases are not in the
file); penalties reflect enforcement intensity as well as conduct; US operations only.

Source: EPA ECHO ICIS-FE&C bulk download, https://echo.epa.gov/tools/data-downloads
        (case pages: https://echo.epa.gov/enforcement-case-report?id=<CASE_NUMBER>)
Run:    python run.py build environmental epa_penalty_intensity

Output: environmental/indicators/epa_penalty_intensity.csv
Owner:  Arash
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from common.io import cached_download, load_universe, today_utc, write_indicator  # noqa: E402
from social.scripts._company_match import CompanyMatcher  # noqa: E402
from environmental.scripts._revenue import load_revenue  # noqa: E402

CATEGORY = "environmental"
INDICATOR_ID = "epa_penalty_intensity"
SOURCE = "EPA ECHO ICIS-FE&C civil enforcement cases"
ZIP_URL = "https://echo.epa.gov/files/echodownloads/case_downloads.zip"
CASE_URL = "https://echo.epa.gov/enforcement-case-report?id={case}"
WINDOW = 5
FIRST_YEAR, LAST_YEAR = 2020, 2025  # window ends; 2025 is the last complete settlement year


def load_cases() -> tuple[pd.DataFrame, pd.DataFrame]:
    """-> (penalties per case: case_number, year, penalty_usd), (defendants: case_number, name)."""
    path = cached_download(ZIP_URL, CATEGORY, "epa_echo/case_downloads.zip")
    with zipfile.ZipFile(path) as z:
        concl = pd.read_csv(z.open("CASE_ENFORCEMENT_CONCLUSIONS.csv"), dtype=str, encoding="latin-1")
        defs = pd.read_csv(z.open("CASE_DEFENDANTS.csv"), dtype=str, encoding="latin-1")

    amount = sum(pd.to_numeric(concl[c], errors="coerce").fillna(0)
                 for c in ["FED_PENALTY_ASSESSED_AMT", "STATE_LOCAL_PENALTY_AMT"])
    date = pd.to_datetime(concl["SETTLEMENT_ENTERED_DATE"], format="%m/%d/%Y", errors="coerce")
    date = date.fillna(pd.to_datetime(concl["SETTLEMENT_LODGED_DATE"], format="%m/%d/%Y", errors="coerce"))
    year = date.dt.year.fillna(pd.to_numeric(concl["SETTLEMENT_FY"], errors="coerce"))
    concl = concl.assign(penalty_usd=amount, year=year).dropna(subset=["year"])
    concl = concl[concl["penalty_usd"] > 0]
    # a case can have several conclusions (e.g. a consent decree per defendant group): sum
    # them, dated by the latest conclusion
    cases = concl.groupby("CASE_NUMBER").agg(penalty_usd=("penalty_usd", "sum"), year=("year", "max")).reset_index()
    cases["year"] = cases["year"].astype(int)

    named = defs[defs["NAMED_IN_SETTLEMENT_FLAG"].eq("Y")]
    defs = pd.concat([named, defs[~defs["CASE_NUMBER"].isin(named["CASE_NUMBER"])]])  # all defendants if none flagged
    names = defs[["CASE_NUMBER", "DEFENDANT_NAME"]].dropna().drop_duplicates()
    # cases without a defendant row: the conclusion name is the respondent
    missing = concl[~concl["CASE_NUMBER"].isin(names["CASE_NUMBER"])][["CASE_NUMBER", "ENF_CONCLUSION_NAME"]]
    names = pd.concat([names, missing.rename(columns={"ENF_CONCLUSION_NAME": "DEFENDANT_NAME"})]).dropna().drop_duplicates()
    names = names[names["CASE_NUMBER"].isin(cases["CASE_NUMBER"])]
    return cases, names.rename(columns={"CASE_NUMBER": "case_number", "DEFENDANT_NAME": "name"})


def build() -> pd.DataFrame:
    universe = load_universe()
    cik_to_tickers: dict[str, list[str]] = {}
    for t, c in zip(universe["ticker"], universe["cik"]):
        cik_to_tickers.setdefault(str(c).zfill(10), []).append(t)

    cases, names = load_cases()
    cases = cases[cases["year"].between(FIRST_YEAR - WINDOW + 1, LAST_YEAR)]
    names = names[names["case_number"].isin(cases["CASE_NUMBER"])].copy()
    names["n_defendants"] = names.groupby("case_number")["name"].transform("nunique")

    matched = CompanyMatcher().match(pd.Series([None] * len(names), index=names.index), names["name"])
    names = names.join(matched)
    hits = names.dropna(subset=["cik"]).merge(cases, left_on="case_number", right_on="CASE_NUMBER")
    hits["share_usd"] = hits["penalty_usd"] / hits["n_defendants"]
    hits = hits.drop_duplicates(["case_number", "cik"])  # parent + subsidiary on one case count once
    hits = hits.sort_values("share_usd", ascending=False)
    log_path = Path(__file__).resolve().parents[1] / "raw" / "epa_penalty_matches.csv"
    hits[["case_number", "year", "name", "cik", "match", "n_defendants", "penalty_usd", "share_usd"]].to_csv(log_path, index=False)
    print(f"cases with a penalty {FIRST_YEAR - WINDOW + 1}-{LAST_YEAR}: {len(cases)}; "
          f"matched to S&P 500: {hits['case_number'].nunique()} cases, {hits['cik'].nunique()} companies")

    revenue = load_revenue()
    rows = []
    for cik, tickers in cik_to_tickers.items():
        own = hits[hits["cik"] == cik]
        for end in range(FIRST_YEAR, LAST_YEAR + 1):
            years = range(end - WINDOW + 1, end + 1)
            revs = [revenue[(tickers[0], y)] for y in years if (tickers[0], y) in revenue]
            if len(revs) < 3:
                continue  # not enough revenue history for a fair denominator
            in_window = own[own["year"].isin(years)]
            total = float(in_window["share_usd"].sum())
            value = total / (sum(revs) / len(revs) / 1e9)
            if in_window.empty:
                url = "https://echo.epa.gov/facilities/enforcement-case-search"
                note = (f"no federal EPA civil penalty found under the company's name, former names or 10-K "
                        f"subsidiaries with a settlement in {years[0]}-{end} (ECHO file retrieved {today_utc()})")
            else:
                top = in_window.iloc[0]
                url = CASE_URL.format(case=top["case_number"])
                note = (f"{in_window['case_number'].nunique()} case(s), ${total:,.0f} in {years[0]}-{end} over mean revenue "
                        f"${sum(revs) / len(revs) / 1e9:,.1f}bn; largest: case {top['case_number']} ({int(top['year'])}), "
                        f"defendant '{top['name']}', ${top['share_usd']:,.0f}")
            for ticker in tickers:
                rows.append({"ticker": ticker, "year": end, "value": round(value, 2), "source": SOURCE,
                             "source_url": url, "retrieved": today_utc(), "note": note})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
