"""employer_retirement_contribution - what the company pays into its US employees'
401(k)-type retirement plans, per active participant, in USD per year.

What it measures: how much of workers' long-term financial security the employer funds
(matching and profit-sharing contributions), not what workers save themselves. Every
private US retirement plan files a Form 5500 with the Department of Labor; large plans
attach Schedule H with the employer's contributions for the plan year. For each company
we add up all its single-employer defined-contribution plans:
    value = sum(employer contributions) / sum(active participants at year end)
Higher is better. Per participant, so company size does not matter.

Caveats: US plans only. Defined-benefit pension plans are left out (their contributions
depend on funding rules and interest rates, not on generosity), so a company that
mainly offers a pension looks lower than it is.

Plans are linked to companies by sponsor EIN, SEC name or 10-K Exhibit 21 subsidiary
name (social/scripts/_company_match.py). Amended filings replace the original. A
company-year needs >= 100 active participants.

Source: US Department of Labor EBSA, Form 5500 + Schedule H public datasets
        https://www.dol.gov/agencies/ebsa/about-ebsa/our-activities/public-disclosure/foia/form-5500-datasets
Run:    python social/scripts/_subsidiaries.py      # once, shared helper
        python run.py build social employer_retirement_contribution

Output: social/indicators/employer_retirement_contribution.csv
        social/raw/form5500_plans.csv  (every matched plan, for audit)
Owner:  Arash
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.config import raw_dir  # noqa: E402
from common.io import cached_download, today_utc, write_indicator  # noqa: E402
from _company_match import CompanyMatcher  # noqa: E402

CATEGORY = "social"
INDICATOR_ID = "employer_retirement_contribution"
SOURCE = "DOL Form 5500 + Schedule H"
YEARS = [2022, 2023, 2024]
URL = "https://askebsa.dol.gov/FOIA%20Files/{year}/Latest/{name}_{year}_Latest.zip"
MIN_PARTICIPANTS = 100
AUDIT = raw_dir(CATEGORY) / "form5500_plans.csv"

F5500_COLS = [
    "ACK_ID", "FORM_PLAN_YEAR_BEGIN_DATE", "TYPE_PLAN_ENTITY_CD", "PLAN_NAME", "SPONS_DFE_PN",
    "SPONSOR_DFE_NAME", "SPONS_DFE_EIN", "TOT_ACTIVE_PARTCP_CNT", "TYPE_PENSION_BNFT_CODE", "DATE_RECEIVED",
]
SCH_H_COLS = ["ACK_ID", "EMPLR_CONTRIB_INCOME_AMT"]


def read_zip(year: int, name: str, cols: list[str]) -> tuple[pd.DataFrame, str]:
    url = URL.format(year=year, name=name)
    path = cached_download(url, CATEGORY, f"form5500/{name}_{year}_Latest.zip")
    with zipfile.ZipFile(path) as z:  # the zip also holds a *_layout.txt
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        with z.open(csv_name) as fh:
            return pd.read_csv(fh, usecols=cols, dtype=str, encoding="latin-1"), url


def is_defined_contribution(codes: object) -> bool:
    """Pension feature codes come in 2-character pairs: '1x' = defined benefit, '2x' = DC."""
    pairs = re.findall(r"[0-9][A-Z]", str(codes).upper())
    return any(p[0] == "2" for p in pairs) and not any(p[0] == "1" for p in pairs)


def build() -> pd.DataFrame:
    matcher = CompanyMatcher()
    frames = []
    for year in YEARS:
        f, url = read_zip(year, "F_5500", F5500_COLS)
        h, url_h = read_zip(year, "F_SCH_H", SCH_H_COLS)
        f = f[(f["TYPE_PLAN_ENTITY_CD"] == "2") & f["TYPE_PENSION_BNFT_CODE"].map(is_defined_contribution)]
        f = f.merge(h, on="ACK_ID", how="inner")
        f["source_url"] = url
        frames.append(f)
        print(f"{year}: {len(f)} single-employer DC plans with Schedule H")
    plans = pd.concat(frames, ignore_index=True)

    plans["plan_year"] = pd.to_datetime(plans["FORM_PLAN_YEAR_BEGIN_DATE"], errors="coerce").dt.year
    plans["participants"] = pd.to_numeric(plans["TOT_ACTIVE_PARTCP_CNT"], errors="coerce")
    plans["employer_contrib"] = pd.to_numeric(plans["EMPLR_CONTRIB_INCOME_AMT"], errors="coerce")
    plans = plans.dropna(subset=["plan_year", "participants", "employer_contrib"])
    plans = plans[plans["plan_year"].isin(YEARS) & (plans["participants"] > 0) & (plans["employer_contrib"] >= 0)]
    # Amended filings: keep the latest filing per plan (sponsor EIN + plan number) and plan year.
    plans = plans.sort_values(["DATE_RECEIVED", "ACK_ID"]).drop_duplicates(
        ["SPONS_DFE_EIN", "SPONS_DFE_PN", "plan_year"], keep="last"
    )

    m = matcher.match(plans["SPONS_DFE_EIN"], plans["SPONSOR_DFE_NAME"])
    plans = plans.join(m)[m["cik"].notna()]
    print(f"matched {len(plans)} plans to {plans['cik'].nunique()} companies ({plans['match'].value_counts().to_dict()})")

    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    plans.sort_values(["cik", "plan_year", "ACK_ID"])[
        ["plan_year", "cik", "match", "ACK_ID", "SPONSOR_DFE_NAME", "SPONS_DFE_EIN", "SPONS_DFE_PN", "PLAN_NAME",
         "TYPE_PENSION_BNFT_CODE", "participants", "employer_contrib", "DATE_RECEIVED"]
    ].to_csv(AUDIT, index=False, lineterminator="\n")

    g = plans.groupby(["cik", "plan_year"]).agg(
        contrib=("employer_contrib", "sum"), participants=("participants", "sum"), n=("ACK_ID", "size"),
        biggest=("PLAN_NAME", lambda s: s.loc[plans.loc[s.index, "participants"].idxmax()]),
        acks=("ACK_ID", lambda s: " ".join(s.head(5))), source_url=("source_url", "first"),
    ).reset_index()
    small = (g["participants"] < MIN_PARTICIPANTS).sum()
    g = g[g["participants"] >= MIN_PARTICIPANTS]
    print(f"dropped {small} company-years under {MIN_PARTICIPANTS} active participants")

    rows = []
    for r in g.itertuples():
        for ticker in matcher.tickers[r.cik]:
            rows.append({
                "ticker": ticker,
                "year": int(r.plan_year),
                "value": round(r.contrib / r.participants, 2),
                "source": SOURCE,
                "source_url": r.source_url,
                "retrieved": today_utc(),
                "note": (f"employer contributions {int(r.contrib)} USD / {int(r.participants)} active participants "
                         f"in {r.n} DC plan(s); largest: {r.biggest}; ACK_ID {r.acks}; "
                         f"plans listed in social/raw/form5500_plans.csv"),
            })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
