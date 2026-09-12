"""employment_growth - 3-year CAGR of employee headcount, a proxy for the company's
contribution to job creation (the most direct link between a company and the real
economy).

Self-contained: extracts headcount straight from each company's own 10-K filings
(see economic/scripts/_headcount.py for the extraction method and its known
limitations) - does not depend on universe/financials.csv, so it isn't blocked by
whatever state that shared file is in.

For each company: read the latest 10-K's headcount (and, when the filing states
several years in one sentence, up to 3 years for free). If the year 3 fiscal years
back is still missing, fetch that specific older 10-K too. At most 2 filings
downloaded per company.

EXCLUDE_TICKERS: companies where the extraction is known to give a wrong number and
there's no single "total" sentence to fall back on - documented per ticker instead of
silently guessing. NextEra Energy states two subsidiaries' headcounts (FPL, NEER)
separately and never states a consolidated total in prose, so summing them would be
a guess, not an extraction.

Owner:  lauren
Source: SEC 10-K filings, "Human Capital" disclosures (Item 101(c))
Run:    python run.py build economic employment_growth

Output: economic/indicators/employment_growth.csv in the shared format (docs/DATA_FORMAT.md)
"""

import pandas as pd

from common.io import load_universe, today_utc, write_indicator
from economic.scripts._headcount import ARCHIVE_URL, CIK_OVERRIDES, extract_headcount, fetch_filing_list

CATEGORY = "economic"
INDICATOR_ID = "employment_growth"
SOURCE = "SEC 10-K Human Capital disclosures"
CAGR_YEARS = 3

EXCLUDE_TICKERS = {
    "NEE": "10-K states FPL and NEER subsidiary headcounts separately (9,400 / 7,900 in "
    "the 2025 filing), never a consolidated NextEra Energy total in prose - no reliable "
    "single number to extract.",
}


def _doc_url(cik: str, ticker: str, accession: str, primary_doc: str) -> str:
    cik = CIK_OVERRIDES.get(ticker, cik)
    return ARCHIVE_URL.format(cik_int=int(cik), accn_nodash=accession.replace("-", ""), doc=primary_doc)


def _headcount_for_company(cik: str, ticker: str, filings: pd.DataFrame) -> dict:
    """year -> (value, quote, source_url), from as few filings as the CAGR needs."""
    found = {}

    def add_from_filing(row):
        cands = extract_headcount(cik, ticker, row["accessionNumber"], row["primaryDocument"], row["reportDate"])
        url = _doc_url(cik, ticker, row["accessionNumber"], row["primaryDocument"])
        for c in cands:
            found.setdefault(c.year, (c.value, c.quote, url))

    if filings.empty:
        return found
    add_from_filing(filings.iloc[0])
    if not found:
        return found

    latest_year = max(found)
    prior_target = latest_year - CAGR_YEARS
    if prior_target not in found:
        report_years = filings["reportDate"].str[:4].astype(int)
        older = filings[report_years == prior_target]
        if not older.empty:
            add_from_filing(older.iloc[0])

    return found


def build() -> pd.DataFrame:
    universe = load_universe()  # ticker, name, sector, cik

    rows = []
    for _, co in universe.iterrows():
        ticker, cik = co["ticker"], co["cik"]
        if ticker in EXCLUDE_TICKERS:
            continue
        filings = fetch_filing_list(cik, ticker)
        found = _headcount_for_company(cik, ticker, filings)
        if not found:
            continue

        for year in sorted(found):
            prior_year = year - CAGR_YEARS
            if prior_year not in found:
                continue
            emp_now, quote_now, url_now = found[year]
            emp_prior, quote_prior, _ = found[prior_year]
            if emp_now <= 0 or emp_prior <= 0:
                continue
            cagr = (emp_now / emp_prior) ** (1 / CAGR_YEARS) - 1
            rows.append(
                {
                    "ticker": ticker,
                    "year": int(year),
                    "value": round(cagr, 4),
                    "source": SOURCE,
                    "source_url": url_now,
                    "retrieved": today_utc(),
                    "note": f"employees {emp_prior:,} ({prior_year}) -> {emp_now:,} ({year}), 3y CAGR. "
                    f'{year} quote: "{quote_now}" | {prior_year} quote: "{quote_prior}"',
                }
            )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
