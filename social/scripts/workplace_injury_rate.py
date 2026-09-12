"""workplace_injury_rate - OSHA total recordable injury & illness rate (TRIR) of a
company's US establishments: recordable cases per 100 full-time workers per year.

What it measures: how often people get hurt or sick at work for this company. Every US
establishment with 250+ employees (20+ in high-hazard industries) must file its OSHA
Form 300A summary electronically; OSHA publishes all of them. For each company we add
up the cases and hours of the establishments it filed under, then
    TRIR = (days-away + restricted/transfer + other recordable cases) * 200,000 / hours
200,000 hours = 100 full-time workers for a year (the standard OSHA/BLS convention).
Lower is better. It is a rate, so company size does not matter.

Coverage caveat: industries OSHA exempts from record keeping (banks, insurers, software,
real estate, ...) do not file, and railroads/airlines report elsewhere, so those
companies have no row - a missing row, never a zero.

Establishments are linked to companies by EIN, SEC name or 10-K Exhibit 21 subsidiary
name (social/scripts/_company_match.py). A company-year needs >= 500,000 reported hours
(~250 full-time workers) so a single small site does not stand in for a whole company.
Rows with implausible hours (< 500 or > 4,000 per average employee) are dropped as
data-entry errors.

Source: OSHA Injury Tracking Application (ITA), Form 300A summary data
        https://www.osha.gov/Establishment-Specific-Injury-and-Illness-Data
Run:    python social/scripts/_subsidiaries.py      # once, shared helper
        python run.py build social workplace_injury_rate

Output: social/indicators/workplace_injury_rate.csv
        social/raw/osha_establishments.csv  (every matched establishment, for audit)
Owner:  Arash
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.io import cached_download, today_utc, write_indicator  # noqa: E402
from common.config import raw_dir  # noqa: E402
from _company_match import CompanyMatcher  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "workplace_injury_rate"
SOURCE = "OSHA ITA Form 300A summary data"

BASE = "https://www.osha.gov/sites/default/files/"
FILES = {  # data year -> published file (the latest release per year)
    2022: "ITA-data-cy2022.zip",
    2023: "ITA_300A_Summary_Data_2023_through_12-31-2024.zip",
    2024: "ITA_300A_Summary_Data_2024_through_12-31-2025.zip",
}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"}

COLS = [
    "id", "establishment_id", "company_name", "establishment_name", "ein", "state", "naics_code",
    "establishment_type", "annual_average_employees", "total_hours_worked", "total_dafw_cases",
    "total_djtr_cases", "total_other_cases", "year_filing_for", "created_timestamp",
]
MIN_HOURS = 500_000
AUDIT = raw_dir(CATEGORY) / "osha_establishments.csv"


def load_year(year: int) -> pd.DataFrame:
    path = cached_download(BASE + FILES[year], CATEGORY, f"osha/{FILES[year]}", headers=BROWSER)
    df = pd.read_csv(path, compression="zip", usecols=COLS, dtype={"ein": str, "naics_code": str},
                     encoding="utf-8-sig", low_memory=False)
    df = df[df["year_filing_for"] == year].copy()
    df["source_url"] = BASE + FILES[year]
    for c in ["annual_average_employees", "total_hours_worked", "total_dafw_cases", "total_djtr_cases", "total_other_cases"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # An establishment can appear more than once after corrections: keep its last submission.
    df["created"] = pd.to_datetime(df["created_timestamp"], errors="coerce")
    df = df.sort_values(["created", "id"]).drop_duplicates(["establishment_id", "year_filing_for"], keep="last")
    return df


def build() -> pd.DataFrame:
    matcher = CompanyMatcher()
    frames = []
    for year in FILES:
        df = load_year(year)
        n_all = len(df)
        df = df[df["establishment_type"].fillna(1).astype(int) == 1]  # private sector only
        hpe = df["total_hours_worked"] / df["annual_average_employees"]
        df = df[(df["total_hours_worked"] > 0) & hpe.between(500, 4000)]
        df = df.dropna(subset=["total_dafw_cases", "total_djtr_cases", "total_other_cases"])
        m = matcher.match(df["ein"], df["company_name"])
        df = df.join(m)[m["cik"].notna()]
        print(f"{year}: {n_all} establishments, {len(df)} matched to {df['cik'].nunique()} companies "
              f"({df['match'].value_counts().to_dict()})")
        frames.append(df)
    est = pd.concat(frames, ignore_index=True)
    est["cases"] = est["total_dafw_cases"] + est["total_djtr_cases"] + est["total_other_cases"]

    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    est.sort_values(["cik", "year_filing_for", "id"])[
        ["year_filing_for", "cik", "match", "id", "establishment_id", "company_name", "establishment_name", "ein",
         "state", "naics_code", "annual_average_employees", "total_hours_worked", "total_dafw_cases",
         "total_djtr_cases", "total_other_cases"]
    ].to_csv(AUDIT, index=False, lineterminator="\n")

    g = est.groupby(["cik", "year_filing_for"]).agg(
        cases=("cases", "sum"), hours=("total_hours_worked", "sum"), employees=("annual_average_employees", "sum"),
        sites=("id", "size"), dafw=("total_dafw_cases", "sum"), djtr=("total_djtr_cases", "sum"),
        by_ein=("match", lambda s: int((s == "ein").sum())), by_name=("match", lambda s: int((s == "name").sum())),
        by_sub=("match", lambda s: int((s == "subsidiary").sum())), source_url=("source_url", "first"),
    ).reset_index()
    small = (g["hours"] < MIN_HOURS).sum()
    g = g[g["hours"] >= MIN_HOURS]
    print(f"dropped {small} company-years under {MIN_HOURS:,} reported hours")

    rows = []
    for r in g.itertuples():
        for ticker in matcher.tickers[r.cik]:
            rows.append({
                "ticker": ticker,
                "year": int(r.year_filing_for),
                "value": round(r.cases * 200_000 / r.hours, 3),
                "source": SOURCE,
                "source_url": r.source_url,
                "retrieved": today_utc(),
                "note": (f"{int(r.cases)} recordable cases ({int(r.dafw)} days-away, {int(r.djtr)} restricted) / "
                         f"{int(r.hours)} hours at {r.sites} establishments, {int(r.employees)} avg employees; "
                         f"matched by ein {r.by_ein}, sec name {r.by_name}, ex-21 subsidiary {r.by_sub}; "
                         f"sites listed in social/raw/osha_establishments.csv"),
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
