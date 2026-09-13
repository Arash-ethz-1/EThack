"""Exhibit - low scores get caught later.

Question: if our method had been run at the end of 2021, would the companies it rated
worst have been the ones regulators fined afterwards? A score that only reflects
self-reported claims would not know; a score that measures real behaviour should.

How (deterministic, no model):
  1. Rebuild every ready indicator AS OF 2021: each company's latest value with year <= 2021.
     Indicators without data that early drop out (they could not have been used then).
     The outcome must not be an input: epa_penalty_intensity (the fines themselves),
     labor_litigation_intensity and sbti_climate_target (a 2026 snapshot) are left out.
  2. Score with the balanced category weights, ranked WITHIN each GICS sector (so "fined
     more" cannot just mean "is a utility") - common/score.py, same code as the dashboard.
  3. Split each sector into five equal groups by that 2021 score (Q1 worst ... Q5 best).
  4. Outcome: did the company (or a 10-K subsidiary) receive a federal EPA civil penalty
     settled 2022-2025? (EPA ECHO, environmental/raw/epa_penalty_matches.csv)
  Also tested, reported in the verdict: federal employment lawsuits per $bn 2022-2025 by
  the social score without the litigation indicator - no pattern.

Limits: 2021 scores rest on the indicators that existed then (listed in numbers); larger
companies have more facilities and so more chances to be fined - the score is size-
neutral, the outcome is not; today's S&P 500 members only.

    python run.py verify caught_later
"""

from __future__ import annotations

import pandas as pd

from common.config import ROOT, UNIVERSE_CSV, indicator_path
from common.score import Dataset, Profile, latest, load_dataset, load_profile, score_profile

TITLE = "Low scores get caught later"
KIND = "code"
EXHIBIT = "A"
AS_OF = 2021
OUTCOME_YEARS = (2022, 2025)
LEFT_OUT = ["epa_penalty_intensity", "labor_litigation_intensity", "sbti_climate_target"]
GROUPS = ["Q1 worst", "Q2", "Q3", "Q4", "Q5 best"]


def dataset_as_of(data: Dataset, left_out: list[str], year: int = AS_OF) -> Dataset:
    catalog = data.catalog[~data.catalog["indicator_id"].isin(left_out)]
    values, years = {}, {}
    for _, row in catalog.iterrows():
        df = pd.read_csv(indicator_path(row["category"], row["indicator_id"]))
        df = df[df["year"] <= year]
        if df.empty:
            continue
        rows = latest(df)
        values[row["indicator_id"]], years[row["indicator_id"]] = rows["value"], rows["year"]
    catalog = catalog[catalog["indicator_id"].isin(values)].reset_index(drop=True)
    tickers = data.universe["ticker"]
    return Dataset(data.universe, catalog, pd.DataFrame(values).reindex(tickers), pd.DataFrame(years).reindex(tickers))


def quintile_rates(score: pd.Series, sectors: pd.Series, outcome: pd.Series) -> list[dict]:
    pct = score.groupby(sectors).rank(pct=True, method="average")
    group = pd.cut(pct, [0, .2, .4, .6, .8, 1.0], labels=GROUPS, include_lowest=True)
    out = []
    for g in GROUPS:
        members = outcome[group == g]
        out.append({"group": g, "companies": int(len(members)), "share": round(float(members.mean()), 4) if len(members) else None,
                    "hits": int(members.sum())})
    return out


def run(profile: Profile | None = None, data: Dataset | None = None) -> dict:
    """`profile`: whose weights to test (default: balanced) - the dashboard passes the user's choice.
    Its category and indicator weights are used; the sector-relative ranking and the 2021 cut-off are fixed."""
    data = data or load_dataset()
    universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)
    universe["cik10"] = universe["cik"].str.zfill(10)
    primary = universe.drop_duplicates("cik10")  # share classes once
    first_ticker = primary.set_index("cik10")["ticker"]

    past = dataset_as_of(data, LEFT_OUT)
    base = profile or load_profile("balanced")
    profile = Profile("caught_later", category_weights=base.category_weights, indicator_weights=base.indicator_weights,
                      sector_relative=True, min_year=2016)
    table = score_profile(past, profile).table.set_index("ticker")
    table = table[table.index.isin(primary["ticker"])].dropna(subset=["total_score"])

    matches = pd.read_csv(ROOT / "environmental" / "raw" / "epa_penalty_matches.csv", dtype={"cik": str})
    matches["ticker"] = matches["cik"].str.zfill(10).map(first_ticker)
    fined = matches[matches["year"].between(*OUTCOME_YEARS)]
    outcome = pd.Series(table.index.isin(set(fined["ticker"].dropna())).astype(float), index=table.index)

    total = quintile_rates(table["total_score"], table["sector"], outcome)
    env = quintile_rates(table["environmental_score"].dropna(), table["sector"], outcome.reindex(table["environmental_score"].dropna().index))

    # the second outcome we tried: lawsuits by the social score without the litigation indicator
    lit = pd.read_csv(indicator_path("social", "labor_litigation_intensity"))
    future_lit = lit[lit["year"].between(*OUTCOME_YEARS)].groupby("ticker")["value"].median()
    soc = table["social_score"].dropna()
    soc_pct = soc.groupby(table["sector"]).rank(pct=True)
    lit_group = pd.cut(soc_pct, [0, .2, .4, .6, .8, 1.0], labels=GROUPS, include_lowest=True)
    lit_rows = [{"group": g, "median_lawsuits_per_bn": round(float(future_lit.reindex(soc.index)[lit_group == g].median()), 3)} for g in GROUPS]

    worst, best = total[0]["share"], total[-1]["share"]
    ratio = worst / best if best else None
    held = worst is not None and best is not None and worst > best
    verdict = (
        f"Of the companies our method would have rated worst in their sector at the end of 2021, "
        f"{worst:.0%} were fined by the EPA in 2022-2025 - against {best:.0%} of the best-rated"
        + (f" ({ratio:.1f}x)." if ratio else ".")
        + " Employee lawsuits showed no such pattern."
    )
    return {
        "status": "passed" if held else "flagged",
        "verdict": verdict,
        "numbers": {
            "as_of": AS_OF,
            "outcome_years": list(OUTCOME_YEARS),
            "companies": int(len(table)),
            "fined": int(outcome.sum()),
            "indicators_used": list(past.catalog["indicator_id"]),
            "left_out": LEFT_OUT,
            "total_score": total,
            "environmental_score": env,
            "lawsuits_by_social_score": lit_rows,
            "worst_to_best_ratio": round(ratio, 2) if ratio else None,
        },
        "rows": [
            {"ticker": t, "year": int(r["year"]), "indicator_id": "epa_penalty", "value": float(r["share_usd"]),
             "detail": f"2021 total score {table.at[t, 'total_score']:.0f} - EPA case {r['case_number']} ({r['name']})",
             "url": f"https://echo.epa.gov/enforcement-case-report?id={r['case_number']}"}
            for t, r in fined.dropna(subset=["ticker"]).sort_values("share_usd", ascending=False).drop_duplicates("ticker").set_index("ticker").iterrows()
            if t in table.index
        ][:40],
    }
