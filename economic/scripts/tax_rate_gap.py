"""tax_rate_gap - gap between the US federal statutory tax rate (21%) and the company's
effective tax rate (income tax expense / pretax income). A larger gap means paying
further below statutory - a proxy for reduced contribution to public finances.

Note: benchmarked against the flat US federal rate only, not a blended multinational
statutory rate (state + foreign mix varies by company and isn't cleanly tagged in XBRL).

Owner:  lauren
Source: SEC XBRL company facts (data.sec.gov/api/xbrl/companyfacts)
Run:    python run.py build economic tax_rate_gap

Output: economic/indicators/tax_rate_gap.csv in the shared format (docs/DATA_FORMAT.md)
"""

import pandas as pd

from common.io import load_universe, today_utc, write_indicator
from economic.scripts._xbrl import COMPANYFACTS_URL, annual_usd_facts, fetch_companyfacts

CATEGORY = "economic"
INDICATOR_ID = "tax_rate_gap"
SOURCE = "SEC XBRL companyfacts"
STATUTORY_RATE = 0.21

TAX_EXPENSE_TAGS = ["IncomeTaxExpenseBenefit"]
PRETAX_INCOME_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
]


def build() -> pd.DataFrame:
    universe = load_universe()  # ticker, name, sector, cik

    rows = []
    for _, co in universe.iterrows():
        facts = fetch_companyfacts(co["cik"], co["ticker"])
        if facts is None:
            continue

        tax = annual_usd_facts(facts, TAX_EXPENSE_TAGS)
        pretax = annual_usd_facts(facts, PRETAX_INCOME_TAGS)
        if tax.empty or pretax.empty:
            continue

        merged = tax.merge(pretax, on="year", suffixes=("_tax", "_pretax"))
        for _, r in merged.iterrows():
            if r["value_pretax"] <= 0:
                continue  # negative/near-zero pretax income makes the ratio meaningless
            effective_rate = r["value_tax"] / r["value_pretax"]
            gap = STATUTORY_RATE - effective_rate
            rows.append(
                {
                    "ticker": co["ticker"],
                    "year": int(r["year"]),
                    "value": round(gap, 4),
                    "source": SOURCE,
                    "source_url": COMPANYFACTS_URL.format(cik=str(co["cik"]).zfill(10)),
                    "retrieved": today_utc(),
                    "note": f"effective_rate={effective_rate:.4f} (tax={r['value_tax']:.0f}, "
                    f"pretax={r['value_pretax']:.0f}), accn={r['accn_tax']}",
                }
            )

    return pd.DataFrame(rows)


if __name__ == "__main__":
    write_indicator(CATEGORY, INDICATOR_ID, build())
