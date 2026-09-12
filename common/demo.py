"""SYNTHETIC demo data so the pipeline and dashboard can be built before real indicators exist.

Every number here is random. Companies are called DEMO001, DEMO002, ... on purpose so
nobody mistakes them for real S&P 500 companies. This data is never written to the
indicator folders and must never be presented as a result.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.score import Dataset

SECTORS = [
    "Communication Services", "Consumer Discretionary", "Consumer Staples", "Energy",
    "Financials", "Health Care", "Industrials", "Information Technology",
    "Materials", "Real Estate", "Utilities",
]
HEAVY_EMITTERS = {"Energy", "Utilities", "Materials"}

# The candidate indicators from docs/tasks/*.md - names only, values below are random.
DEMO_CATALOG = [
    # category, id, name, unit, higher_is_better, (log-mean, log-sd) of the random values
    ("economic", "effective_tax_rate", "Effective tax rate", "%", "true", (3.0, 0.35)),
    ("economic", "rd_intensity", "R&D intensity", "% of revenue", "true", (1.2, 1.0)),
    ("economic", "capex_intensity", "Capex intensity", "% of revenue", "true", (1.8, 0.7)),
    ("social", "ceo_pay_ratio", "CEO-to-median-worker pay ratio", "ratio", "false", (5.2, 0.8)),
    ("social", "board_gender_diversity", "Women on the board", "%", "true", (3.4, 0.3)),
    ("social", "injury_rate", "Work injuries per 100 employees", "per 100 employees", "false", (0.3, 0.9)),
    ("environmental", "ghg_intensity", "Scope 1 GHG intensity", "tCO2e per $M revenue", "false", (3.0, 1.4)),
    ("environmental", "toxic_releases", "Toxic releases intensity", "lbs per $M revenue", "false", (2.0, 1.6)),
    ("environmental", "env_violations", "Environmental penalties", "USD per $M revenue", "false", (1.0, 1.5)),
]


def demo_dataset(n_companies: int = 150, seed: int = 7) -> Dataset:
    rng = np.random.default_rng(seed)
    tickers = [f"DEMO{i:03d}" for i in range(1, n_companies + 1)]
    sectors = rng.choice(SECTORS, size=n_companies)
    universe = pd.DataFrame({"ticker": tickers, "name": [f"Demo Company {t[4:]}" for t in tickers], "sector": sectors})

    heavy = np.isin(sectors, list(HEAVY_EMITTERS))
    values, years = {}, {}
    for category, iid, _, _, _, (mu, sd) in DEMO_CATALOG:
        v = rng.lognormal(mu, sd, n_companies)
        if category == "environmental":
            v = np.where(heavy, v * 8, v)  # so sector-relative ranking visibly changes something
        missing = rng.random(n_companies) < 0.15
        values[iid] = pd.Series(np.where(missing, np.nan, v.round(3)), index=tickers)
        years[iid] = pd.Series(np.where(missing, np.nan, rng.choice([2023, 2024], n_companies)), index=tickers)

    catalog = pd.DataFrame(
        [
            {"indicator_id": iid, "name": name, "description": "DEMO - random values", "unit": unit,
             "higher_is_better": hib, "weight": "1", "owner": "demo", "source": "synthetic",
             "status": "ready", "category": category}
            for category, iid, name, unit, hib, _ in DEMO_CATALOG
        ]
    )
    values_df, years_df = pd.DataFrame(values), pd.DataFrame(years)
    values_df.index.name = years_df.index.name = "ticker"
    return Dataset(universe, catalog, values_df, years_df, demo=True)
