"""employment_growth - 3-year CAGR of employee headcount, a proxy for the company's
contribution to job creation (the most direct link between a company and the real
economy).

Source: universe/financials.csv `employees` column (built by Arash/Jean from 10-K
"Human Capital" disclosures, employees_source_url/employees_note per row).

Known issue, worked around here: some employees_note quotes describe a segment,
division or subsidiary headcount rather than the whole company (e.g. Zoetis's 2021
and 2025 rows say "our sales organization consisted of approximately 3,900
employees" - a fraction of its real ~14,500 total). Found by scanning employees_note
for segment/division/subsidiary language and reading the flagged quotes by hand.
EXCLUDE_TICKERS below are the ones confirmed or strongly suspected wrong this way -
skipped entirely rather than risk shipping a wrong number. This is not a full
guarantee the remaining rows are clean (the scan only catches quotes that mention a
sub-unit by name), just the ones caught so far. Flag anything else you spot to
Arash/Jean - it's their file (universe/financials.csv), not ours to edit.

Owner:  lauren
Source: universe/financials.csv employees column
Run:    python run.py build economic employment_growth

Output: economic/indicators/employment_growth.csv in the shared format (docs/DATA_FORMAT.md)
"""

import pandas as pd

from common.config import ROOT
from common.io import today_utc, write_indicator

CATEGORY = "economic"
INDICATOR_ID = "employment_growth"
SOURCE = "universe/financials.csv (10-K Human Capital disclosures)"
CAGR_YEARS = 3

# Confirmed or strongly suspected to be a segment/division/subsidiary headcount, not
# the whole company - see the module docstring. Quote is the exact employees_note text.
EXCLUDE_TICKERS = {
    "AMCR": 'quote says "the Rigid Packaging Segment employed approximately 6,000" - Amcor total is ~41,000',
    "APO": 'quote says "Our Asset Management segment had a team of 2,540 employees"',
    "BRO": 'quote says "our Retail segment employed 6,301 employees"',
    "CRH": 'quote says "The Division employs approximately 46,400 people"',
    "JBHT": 'quote says "The DCS segment employed 14,709 people, including 12,632 drivers"',
    "MRSH": 'quote reads as segment-scoped: "[segment] generated ~61% of revenue and employs approximately 48,800 colleagues"',
    "ZTS": 'quote says "our sales organization consisted of approximately 3,900 employees" (2025) - real 10-K total is 14,500',
    "SMCI": 'quote says "we had over 3,500 employees in our research and development organization" (2026) - same 10-K states '
    'the real total elsewhere: "we employed over 7,000 employees, consisting of approximately 3,500 [R&D] ... 600 '
    'engaged in general and administrative, and approximately 2,100 engaged in manufacturing" - found via spot-check, '
    "not the keyword scan (no segment/division/subsidiary word in the bad quote)",
}


def build() -> pd.DataFrame:
    financials = pd.read_csv(ROOT / "universe" / "financials.csv")
    financials = financials.dropna(subset=["employees"])
    financials = financials[~financials["ticker"].isin(EXCLUDE_TICKERS)]

    rows = []
    for ticker, grp in financials.groupby("ticker"):
        by_year = grp.set_index("year")
        for year in sorted(by_year.index):
            prior_year = year - CAGR_YEARS
            if prior_year not in by_year.index:
                continue
            emp_now = by_year.loc[year, "employees"]
            emp_prior = by_year.loc[prior_year, "employees"]
            if emp_prior <= 0 or emp_now <= 0:
                continue
            cagr = (emp_now / emp_prior) ** (1 / CAGR_YEARS) - 1
            rows.append(
                {
                    "ticker": ticker,
                    "year": int(year),
                    "value": round(cagr, 4),
                    "source": SOURCE,
                    "source_url": by_year.loc[year, "employees_source_url"],
                    "retrieved": today_utc(),
                    "note": f"employees {int(emp_prior):,} ({int(prior_year)}) -> {int(emp_now):,} ({int(year)}), "
                    f"3y CAGR; {by_year.loc[year, 'employees_note']}",
                }
            )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
