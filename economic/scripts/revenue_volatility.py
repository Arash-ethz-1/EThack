"""revenue_volatility - coefficient of variation of year-over-year revenue growth over
the trailing 5 fiscal years (6 annual revenue values -> 5 growth rates). Higher volatility
means a less predictable economic contribution to workers, suppliers and tax receipts.

Note: skips companies whose mean growth over the window is near zero - the coefficient
of variation (stdev / |mean|) is numerically unstable there, and a fabricated huge number
would be worse than a missing row. Also inherits the standard XBRL caveat: an acquisition
or divestiture can spike revenue with no organic change.

Owner:  lauren
Source: SEC XBRL company facts (data.sec.gov/api/xbrl/companyfacts)
Run:    python run.py build economic revenue_volatility

Output: economic/indicators/revenue_volatility.csv in the shared format (docs/DATA_FORMAT.md)
"""

import pandas as pd

from common.io import load_universe, today_utc, write_indicator
from economic.scripts._xbrl import COMPANYFACTS_URL, annual_usd_facts, fetch_companyfacts

CATEGORY = "economic"
INDICATOR_ID = "revenue_volatility"
SOURCE = "SEC XBRL companyfacts"
REVENUE_TAGS = [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
]
WINDOW_YEARS = 6  # -> 5 YoY growth rates
MIN_ABS_MEAN_GROWTH = 0.005  # below this, CV blows up on a near-zero denominator


def build() -> pd.DataFrame:
    universe = load_universe()

    rows = []
    for _, co in universe.iterrows():
        facts = fetch_companyfacts(co["cik"], co["ticker"])
        if facts is None:
            continue

        rev = annual_usd_facts(facts, REVENUE_TAGS)
        if len(rev) < WINDOW_YEARS:
            continue

        window = rev.tail(WINDOW_YEARS)
        growth = window["value"].pct_change().dropna()
        if len(growth) < WINDOW_YEARS - 1:
            continue

        mean_growth = growth.mean()
        if abs(mean_growth) < MIN_ABS_MEAN_GROWTH:
            continue  # can't compute a meaningful coefficient of variation here

        cv = growth.std() / abs(mean_growth)
        latest_year = int(window["year"].max())
        rows.append(
            {
                "ticker": co["ticker"],
                "year": latest_year,
                "value": round(cv, 4),
                "source": SOURCE,
                "source_url": COMPANYFACTS_URL.format(cik=str(co["cik"]).zfill(10)),
                "retrieved": today_utc(),
                "note": f"{WINDOW_YEARS}y window ending {latest_year}, mean_growth={mean_growth:.4f}",
            }
        )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
