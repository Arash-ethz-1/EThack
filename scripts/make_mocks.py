# Generate schema-valid fake data for every contract so that no layer is ever
# blocked on an upstream layer. OWNER: Arash.
#
# Run: python run.py mocks
#
# If you change a contract, change this file in the SAME commit. The tests import
# from here, so a drift breaks them immediately - which is the point.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ethack import contracts  # noqa: E402
from ethack.config import MOCK  # noqa: E402

RNG = np.random.default_rng(42)
N_CO = 120
N_FAC = 900
YEARS = list(range(2019, 2024))

SECTORS = [
    "Energy", "Utilities", "Materials", "Industrials", "Consumer Staples",
    "Information Technology", "Health Care", "Financials",
]
# Rough sector emission scale so mock data has a realistic shape and charts look sane.
SECTOR_SCALE = {
    "Energy": 8e6, "Utilities": 1.2e7, "Materials": 3e6, "Industrials": 8e5,
    "Consumer Staples": 3e5, "Information Technology": 6e4,
    "Health Care": 8e4, "Financials": 2e4,
}


def tickers() -> list[str]:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    out, i = [], 0
    while len(out) < N_CO:
        t = letters[i % 26] + letters[(i // 26) % 26] + letters[(i // 7) % 26]
        if t not in out:
            out.append(t)
        i += 1
    return out


def main() -> None:
    Path(MOCK).mkdir(parents=True, exist_ok=True)
    tk = tickers()
    sec = {t: SECTORS[i % len(SECTORS)] for i, t in enumerate(tk)}

    # --- company_financials
    fin = pd.DataFrame({
        "ticker": pd.Series(tk, dtype="string"),
        "cik": np.arange(1000, 1000 + N_CO, dtype="int64"),
        "year": np.full(N_CO, 2023, dtype="int64"),
        "revenue_usd": RNG.lognormal(23, 1.1, N_CO),
        "sector": pd.Series([sec[t] for t in tk], dtype="string"),
    })
    fin["ebitda_usd"] = fin["revenue_usd"] * RNG.uniform(0.05, 0.35, N_CO)
    fin["capex_usd"] = fin["revenue_usd"] * RNG.uniform(0.02, 0.18, N_CO)
    fin = fin[list(contracts.COMPANY_FINANCIALS)]
    contracts.validate(fin, "company_financials")
    fin.to_parquet(f"{MOCK}/company_financials.parquet", index=False)

    # --- facility_emissions + facility_ticker
    owner = RNG.choice(tk, N_FAC)
    scale = np.array([SECTOR_SCALE[sec[t]] for t in owner])
    rows = []
    for y in YEARS:
        drift = RNG.uniform(0.93, 1.03, N_FAC) ** (y - 2019)
        rows.append(pd.DataFrame({
            "facility_id": np.arange(1_000_000, 1_000_000 + N_FAC, dtype="int64"),
            "year": np.full(N_FAC, y, dtype="int64"),
            "facility_name": pd.Series(
                [f"Mock Facility {i}" for i in range(N_FAC)], dtype="string"),
            "parent_company_raw": pd.Series(
                [f"{t} MOCK SUBSIDIARY LLC (100%)" for t in owner], dtype="string"),
            "ownership_pct": np.full(N_FAC, 100.0),
            "naics": pd.Series(RNG.choice(["221112", "324110", "327310", "331110"],
                                          N_FAC), dtype="string"),
            "state": pd.Series(RNG.choice(["TX", "CA", "LA", "PA", "OH"], N_FAC),
                               dtype="string"),
            "lat": RNG.uniform(25, 48, N_FAC),
            "lon": RNG.uniform(-124, -70, N_FAC),
            "co2e_t": RNG.lognormal(0, 0.8, N_FAC) * scale / 6 * drift,
        }))
    fac = pd.concat(rows, ignore_index=True)[list(contracts.FACILITY_EMISSIONS)]
    contracts.validate(fac, "facility_emissions")
    fac.to_parquet(f"{MOCK}/facility_emissions.parquet", index=False)

    link = pd.DataFrame({
        "facility_id": np.arange(1_000_000, 1_000_000 + N_FAC, dtype="int64"),
        "ticker": pd.Series(owner, dtype="string"),
        "confidence": RNG.uniform(0.62, 1.0, N_FAC),
        "match_method": pd.Series(
            RNG.choice(["ex21_exact", "ex21_embed", "manual"], N_FAC,
                       p=[0.62, 0.30, 0.08]), dtype="string"),
    })
    contracts.validate(link, "facility_ticker")
    link.to_parquet(f"{MOCK}/facility_ticker.parquet", index=False)

    # --- company_reported: deliberately inject a Say-Do gap in ~18% of names,
    #     so downstream charts have the shape we are hunting for. MOCK ONLY.
    metered = (fac[fac.year == 2023]
               .assign(ticker=owner)
               .groupby("ticker")["co2e_t"].sum())
    under = RNG.random(len(metered)) < 0.18
    factor = np.where(under, RNG.uniform(0.25, 0.6, len(metered)),
                      RNG.uniform(0.95, 1.12, len(metered)))
    rep = pd.DataFrame({
        "ticker": pd.Series(metered.index, dtype="string"),
        "year": np.full(len(metered), 2023, dtype="int64"),
        "reported_scope1_t": metered.to_numpy() * factor,
        "base_year": pd.array(RNG.choice([2019, 2020, 2021], len(metered)),
                              dtype="Int64"),
        "target_year": pd.array(RNG.choice([2030, 2040, 2050], len(metered)),
                                dtype="Int64"),
        "target_pct": RNG.uniform(0.2, 1.0, len(metered)),
        "assurance_provider": pd.Series(
            RNG.choice(["Deloitte", "ERM CVS", "SGS", None], len(metered)),
            dtype="string"),
        "verbatim_quote": pd.Series(
            ["MOCK DATA - not a real disclosure"] * len(metered), dtype="string"),
        "source_url": pd.Series(["mock://report.pdf"] * len(metered), dtype="string"),
        "page": pd.array(RNG.integers(10, 90, len(metered)), dtype="Int64"),
    })[list(contracts.COMPANY_REPORTED)]
    contracts.validate(rep, "company_reported")
    rep.to_parquet(f"{MOCK}/company_reported.parquet", index=False)

    # --- satellite: noisier view of the same truth
    sat = pd.DataFrame({
        # asset_id embeds the facility id ONLY in mocks, so the test panel can join.
        # Real Climate TRACE assets carry no EPA id - Jean joins them spatially on lat/lon.
        "asset_id": pd.Series(
            [f"ct_{i}" for i in range(1_000_000, 1_000_000 + N_FAC)], dtype="string"),
        "year": np.full(N_FAC, 2023, dtype="int64"),
        "lat": RNG.uniform(25, 48, N_FAC),
        "lon": RNG.uniform(-124, -70, N_FAC),
        "sector": pd.Series(RNG.choice(["power", "refining", "cement"], N_FAC),
                            dtype="string"),
        "co2e_t": fac[fac.year == 2023]["co2e_t"].to_numpy()
                  * RNG.lognormal(0, 0.35, N_FAC),
        "source": pd.Series(["mock_climate_trace"] * N_FAC, dtype="string"),
    })
    contracts.validate(sat, "satellite_emissions")
    sat.to_parquet(f"{MOCK}/satellite_emissions.parquet", index=False)

    # --- company_scores: lets Florian and Harprit start immediately
    vis = RNG.beta(5, 2, N_CO)
    raw = RNG.normal(0, 1, N_CO)
    ci = (1 - vis) * 0.9 + 0.08
    sc = pd.DataFrame({
        "ticker": pd.Series(tk, dtype="string"),
        "sector": pd.Series([sec[t] for t in tk], dtype="string"),
        "score": raw,
        "ci_low": raw - ci,
        "ci_high": raw + ci,
        "tier": pd.Series(pd.cut(raw, 5, labels=list("EDCBA")).astype(str),
                          dtype="string"),
        "visibility": vis,
        "coverage_ratio": RNG.beta(4, 2, N_CO),
        "n_indicators_used": RNG.integers(2, 5, N_CO).astype("int64"),
    })[list(contracts.COMPANY_SCORES)]
    contracts.validate(sc, "company_scores")
    sc.to_parquet(f"{MOCK}/company_scores.parquet", index=False)

    print(f"mocks written to {MOCK}/  ({N_CO} companies, {N_FAC} facilities, "
          f"{len(YEARS)} years)")
    print("NOTE: all values are synthetic. Never put a mock number on a slide.")


if __name__ == "__main__":
    main()
