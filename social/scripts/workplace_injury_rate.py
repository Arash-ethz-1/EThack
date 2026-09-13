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
real estate, restaurants, telecom carriers, ...) do not file, railroads report to the FRA
and mines to MSHA, so those companies have no row - a missing row, never a zero. Searched
by hand and not in the ITA files under any name: AutoZone, Ross, Hasbro, Deckers, United
Rentals, NetApp, Supermicro, PG&E, Centene, Elevance, Quest Diagnostics, IQVIA, CSX,
Norfolk Southern, Union Pacific, Newmont. That caps coverage below 70% of the S&P 500.

Establishments are linked to companies by EIN, SEC name or 10-K Exhibit 21 subsidiary
name (social/scripts/_company_match.py), plus a short reviewed list of filer names the
automatic matcher cannot resolve (NAME_LINKS below: bare brand names like "Carrier",
initials like "PSEG", utility subsidiaries missing from Exhibit 21). A company-year needs
>= 500,000 reported hours (~250 full-time workers) so a single small site does not stand
in for a whole company.

Data-entry errors removed before adding up (each count is printed by the build):
  - hours < 500 or > 4,000 per average employee;
  - the same establishment submitted twice under two ids (identical ZIP code, employees,
    hours and all three case counts within a company-year): kept once;
  - one total copied onto several establishments (identical employees and hours,
    >= 1,000,000 hours each, e.g. Netflix 2024: 8,673 employees on each of 12 sites): the
    hours cannot be split between the sites, so those rows are dropped, and the whole
    company-year if they make up >= 25% of its hours (the rest is no longer representative);
  - zero recordable cases over >= 5,000,000 hours (2,500 full-time workers): even at 0.1
    cases per 100 workers - below the lowest BLS industry averages - 5 cases would be
    expected, so a zero means cases were not entered; the company-year is dropped.

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
from _company_match import CompanyMatcher, normalise  # noqa: E402

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
    "id", "establishment_id", "company_name", "establishment_name", "ein", "state", "zip_code", "naics_code",
    "establishment_type", "annual_average_employees", "total_hours_worked", "total_dafw_cases",
    "total_djtr_cases", "total_other_cases", "year_filing_for", "created_timestamp",
]
# Reviewed links for filers the automatic matcher misses. Each was checked in the OSHA file
# (establishment names, NAICS, states, EIN) before adding. A guard limits a link to the
# NAICS prefixes / states that belong to the company, so an unrelated firm with the same
# short name ("Simon Contractors", NAICS 2373) or the Iowa "Consumers Energy" cooperative
# is not pulled in. normalised company_name -> (ticker, NAICS prefixes or None, states or None)
NAME_LINKS = {
    "carrier": ("CARR", None, None),              # Carrier Corp. HVAC plants/services, Kidde, Automated Logic
    "cdw": ("CDW", ("4234",), None),              # CDW distribution centers (computer wholesale)
    "eversource": ("ES", ("221", "486"), None),   # CT/MA/NH electric and gas utility
    "jacobs": ("J", ("2213", "237", "5413", "5419", "5612"), None),  # Jacobs O&M water plants, engineering
    "simon": ("SPG", ("531",), None),             # Simon malls (lessors of real estate)
    "ppl": ("PPL", ("221", "5511"), ("PA",)),     # PPL Electric Utilities, Pennsylvania
    "lg and e": ("PPL", ("221",), ("KY",)),       # Louisville Gas & Electric (PPL subsidiary)
    "ku": ("PPL", ("221",), ("KY",)),             # Kentucky Utilities (PPL subsidiary)
    "rhode island energy": ("PPL", ("221",), ("RI",)),        # acquired by PPL in May 2022
    "rhode island energy a ppl": ("PPL", ("221",), ("RI",)),
    "aon": ("AON", ("524",), None),               # Aon insurance brokerage office
    "pseg": ("PEG", ("221", "237", "551", "561"), ("NJ", "NY")),  # PSE&G, PSEG Power, PSEG Long Island
    "consumers energy": ("CMS", ("221", "486"), ("MI",)),     # CMS Energy's Michigan utility
    "consolidated edison of ny": ("ED", ("221",), ("NY",)),   # Con Edison of New York
    "orange and rockland utilities": ("ED", ("221",), ("NY", "NJ")),  # Con Edison subsidiary
    "arizona public service": ("PNW", ("221",), ("AZ", "NM")),  # Pinnacle West's utility (APS, Palo Verde)
    "fedex freight": ("FDXF", ("484",), None),    # the business spun off as FedEx Freight in 2026
    "prologis l p": ("PLD", ("531",), None),      # Prologis operating partnership
    "jb hunt": ("JBHT", ("484", "488", "493"), None),
    "j b hunt transport": ("JBHT", ("484", "488", "493"), None),
}
MIN_HOURS = 500_000
COPIED_TOTAL_HOURS = 1_000_000
COPIED_SHARE = 0.25
ZERO_CASES_MAX_HOURS = 5_000_000
AUDIT = raw_dir(CATEGORY) / "osha_establishments.csv"


def load_year(year: int) -> pd.DataFrame:
    path = cached_download(BASE + FILES[year], CATEGORY, f"osha/{FILES[year]}", headers=BROWSER)
    df = pd.read_csv(path, compression="zip", usecols=COLS, dtype={"ein": str, "naics_code": str, "zip_code": str},
                     encoding="utf-8-sig", low_memory=False)
    df = df[df["year_filing_for"] == year].copy()
    df["source_url"] = BASE + FILES[year]
    df["zip5"] = df["zip_code"].fillna("").astype(str).str.strip().str[:5]
    for c in ["annual_average_employees", "total_hours_worked", "total_dafw_cases", "total_djtr_cases", "total_other_cases"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # An establishment can appear more than once after corrections: keep its last submission.
    df["created"] = pd.to_datetime(df["created_timestamp"], errors="coerce")
    df = df.sort_values(["created", "id"]).drop_duplicates(["establishment_id", "year_filing_for"], keep="last")
    return df


def apply_name_links(df: pd.DataFrame, m: pd.DataFrame, matcher: CompanyMatcher) -> pd.DataFrame:
    """Fill rows the matcher left unmatched from NAME_LINKS (guards: NAICS prefix, state)."""
    cik_of = {t: cik for cik, tickers in matcher.tickers.items() for t in tickers}
    norm = df["company_name"].map(normalise)
    naics = df["naics_code"].fillna("").astype(str)
    state = df["state"].fillna("").astype(str).str.upper()
    m = m.copy()
    for name, (ticker, prefixes, states) in NAME_LINKS.items():
        hit = m["cik"].isna() & (norm == name)
        if prefixes:
            hit &= naics.str.startswith(prefixes)
        if states:
            hit &= state.isin(states)
        m.loc[hit, "cik"] = cik_of[ticker]
        m.loc[hit, "match"] = "link"
    return m


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
        m = apply_name_links(df, m, matcher)
        df = df.join(m)[m["cik"].notna()]
        print(f"{year}: {n_all} establishments, {len(df)} matched to {df['cik'].nunique()} companies "
              f"({df['match'].value_counts().to_dict()})")
        frames.append(df)
    est = pd.concat(frames, ignore_index=True)
    key = ["cik", "year_filing_for", "annual_average_employees", "total_hours_worked"]
    n = len(est)
    est = est.drop_duplicates(key + ["zip5", "total_dafw_cases", "total_djtr_cases", "total_other_cases"])
    print(f"dropped {n - len(est)} duplicate submissions (same company-year, ZIP code, employees, hours and cases)")
    copied = est.duplicated(key, keep=False) & (est["total_hours_worked"] >= COPIED_TOTAL_HOURS)
    cy = [est["cik"], est["year_filing_for"]]
    share = est["total_hours_worked"].where(copied, 0).groupby(cy).transform("sum") / est.groupby(cy)["total_hours_worked"].transform("sum")
    whole = share >= COPIED_SHARE
    bad_years = sorted({f"{matcher.tickers[c][0]} {y}" for c, y in zip(est.loc[whole, "cik"], est.loc[whole, "year_filing_for"])})
    print(f"dropped {int((copied & ~whole).sum())} establishments carrying a copied total; "
          f"{len(bad_years)} company-years where copies are >= {COPIED_SHARE:.0%} of the hours dropped whole: {bad_years}")
    est = est[~copied & ~whole]
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
        by_sub=("match", lambda s: int((s == "subsidiary").sum())),
        by_link=("match", lambda s: int((s == "link").sum())), source_url=("source_url", "first"),
    ).reset_index()
    small = (g["hours"] < MIN_HOURS).sum()
    g = g[g["hours"] >= MIN_HOURS]
    print(f"dropped {small} company-years under {MIN_HOURS:,} reported hours")
    zero = (g["cases"] == 0) & (g["hours"] >= ZERO_CASES_MAX_HOURS)
    print(f"dropped {int(zero.sum())} company-years with zero cases over >= {ZERO_CASES_MAX_HOURS:,} hours")
    g = g[~zero]

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
                         f"matched by ein {r.by_ein}, sec name {r.by_name}, ex-21 subsidiary {r.by_sub}, reviewed name link {r.by_link}; "
                         f"sites listed in social/raw/osha_establishments.csv"),
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
