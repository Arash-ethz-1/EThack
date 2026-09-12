"""revenue_volatility - TODO: one sentence on what this measures and why it matters.

Owner:  lauren
Source: TODO name + URL
Run:    python run.py build economic revenue_volatility

Output: economic/indicators/revenue_volatility.csv in the shared format (docs/DATA_FORMAT.md)
"""

import pandas as pd

from common.io import cached_json, load_universe, today_utc, write_indicator

CATEGORY = "economic"
INDICATOR_ID = "revenue_volatility"
SOURCE = "TODO short source name"


def build() -> pd.DataFrame:
    universe = load_universe()  # ticker, name, sector, cik

    rows = []
    # 1. Download with cached_json(url, CATEGORY, "some_file.json") - it saves to
    #    economic/raw/ so we never download the same thing twice.
    # 2. Compute ONE number per company per year. Normalise by size (revenue,
    #    employees, ...) so big companies don't win just by being big.
    # 3. Skip companies without data - never invent or fill in a value.
    #
    # rows.append({
    #     "ticker": "AAPL",
    #     "year": 2024,
    #     "value": 0.123,
    #     "source": SOURCE,
    #     "source_url": "https://...",   # the exact page/API the number came from
    #     "retrieved": today_utc(),
    #     "note": "",
    # })
    raise NotImplementedError("fill in build() - see the steps above")

    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
