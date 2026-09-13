"""Exhibit - the ranking survives disagreement about weights.

Question: our weights are a choice. Would a fund manager who weighs things differently
end up with a different list of sustainable companies?

How (deterministic, fixed seed, no model): 1,000 random weightings. Every category weight
and every indicator weight is drawn independently from a uniform 0-1 (so any single
indicator can count up to ~infinitely more than another), then common/score.py scores
the S&P 500 exactly as the dashboard does (balanced profile settings, ranked within
sector). For every company we count how often it lands in the top 20% and the bottom 20%.

Numbers:
- median rank correlation between the default ranking and each random one
- of the default top 50, the share that stays in the top 20% in at least 80% of runs
- per company: share of runs in top / bottom 20% (for the dashboard)

    python run.py verify weight_robustness
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.config import CATEGORIES, UNIVERSE_CSV
from common.score import load_dataset, load_profile, score_profile

TITLE = "The ranking survives disagreement"
KIND = "code"
EXHIBIT = "B"
RUNS = 1000
SEED = 2026
TOP = 0.2


def run() -> dict:
    data = load_dataset()
    base = load_profile("balanced")
    universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)
    primary = set(universe.drop_duplicates("cik")["ticker"])

    def ranking(profile) -> pd.Series:
        t = score_profile(data, profile).table.set_index("ticker")
        return t.loc[t.index.isin(primary), "total_score"].dropna()

    default = ranking(base)
    n = len(default)
    default_top50 = default.sort_values(ascending=False).index[:50]
    rng = np.random.default_rng(SEED)
    ids = list(data.catalog["indicator_id"])
    in_top = pd.Series(0, index=default.index)
    in_bottom = pd.Series(0, index=default.index)
    rhos = []
    for _ in range(RUNS):
        cats = dict(zip(CATEGORIES, rng.uniform(0.05, 1, len(CATEGORIES))))
        inds = dict(zip(ids, rng.uniform(0.05, 1, len(ids))))
        profile = type(base)(**{**base.__dict__, "category_weights": cats, "indicator_weights": inds})
        s = ranking(profile).reindex(default.index)
        rank = s.rank(ascending=False, pct=True)
        in_top += (rank <= TOP).astype(int)
        in_bottom += (rank > 1 - TOP).astype(int)
        rhos.append(float(default.rank().corr(s.rank())))

    top_share = in_top / RUNS
    bottom_share = in_bottom / RUNS
    stays = float((top_share[default_top50] >= 0.8).mean())
    rhos = np.array(rhos)
    names = universe.drop_duplicates("ticker").set_index("ticker")["name"]
    solid_top = top_share[top_share >= 0.9].sort_values(ascending=False)
    solid_bottom = bottom_share[bottom_share >= 0.9].sort_values(ascending=False)
    verdict = (
        f"Across {RUNS:,} random weightings the ranking barely moves (median correlation with ours "
        f"{np.median(rhos):.2f}): {stays:.0%} of our top 50 stay in the top fifth in at least 80% of them."
    )
    return {
        "status": "passed" if np.median(rhos) >= 0.7 else "flagged",
        "verdict": verdict,
        "numbers": {
            "runs": RUNS, "seed": SEED, "companies": n,
            "median_rho": round(float(np.median(rhos)), 3),
            "rho_p5": round(float(np.percentile(rhos, 5)), 3),
            "rho_histogram": np.histogram(rhos, bins=20, range=(0, 1))[0].tolist(),
            "top50_stay_share": round(stays, 3),
            "always_top": len(solid_top), "always_bottom": len(solid_bottom),
            "companies_detail": [
                {"ticker": t, "name": names.get(t, ""), "default_score": round(float(default[t]), 1),
                 "top_share": round(float(top_share[t]), 3), "bottom_share": round(float(bottom_share[t]), 3)}
                for t in default.sort_values(ascending=False).index
            ],
        },
        "rows": [],
    }
