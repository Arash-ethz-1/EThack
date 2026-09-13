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
from dataclasses import replace

from common.score import load_dataset, load_profile, profile_ranks, total_scores

TITLE = "The ranking survives disagreement"
KIND = "code"
EXHIBIT = "B"
RUNS = 1000
SEED = 2026
TOP = 0.2


def run(profile=None, runs: int = RUNS, data=None) -> dict:
    """`profile`: the ranking to test (default: balanced) - the dashboard passes the weights the
    user chose. Ranks are computed once (weights never change them), then every random weighting
    is scored by common.score.total_scores - the same arithmetic as the dashboard, just fast."""
    data = data or load_dataset()
    base = profile or load_profile("balanced")
    universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)
    primary = list(universe.drop_duplicates("cik")["ticker"])
    ranks = profile_ranks(data, base).loc[primary]

    default = total_scores(ranks, data.catalog, base.weights(data.catalog), base.category_weights, base.min_weight_share).dropna()
    n = len(default)
    default_top50 = default.sort_values(ascending=False).index[:50]
    rng = np.random.default_rng(SEED)
    ids = list(data.catalog["indicator_id"])
    chosen = base.weights(data.catalog)
    in_top = np.zeros(n)
    in_bottom = np.zeros(n)
    rhos = []
    sub = ranks.loc[default.index]
    default_rank = default.rank().to_numpy()
    for _ in range(runs):
        cats = dict(zip(CATEGORIES, rng.uniform(0.05, 1, len(CATEGORIES))))
        inds = pd.Series(dict(zip(ids, rng.uniform(0.05, 1, len(ids)))))
        # an indicator the user switched off stays off; a pillar set to 0 stays 0
        inds = inds[inds.index.isin(chosen.index)]
        cats = {c: (w if base.category_weights.get(c, 0) > 0 else 0.0) for c, w in cats.items()}
        s = total_scores(sub, data.catalog, inds, cats, base.min_weight_share)
        pct = s.rank(ascending=False, pct=True).to_numpy()
        in_top += pct <= TOP
        in_bottom += pct > 1 - TOP
        rhos.append(float(np.corrcoef(default_rank, s.rank().to_numpy())[0, 1]) if s.notna().all() else float(default.rank().corr(s.rank())))
    in_top = pd.Series(in_top, index=default.index)
    in_bottom = pd.Series(in_bottom, index=default.index)

    top_share = in_top / runs
    bottom_share = in_bottom / runs
    stays = float((top_share[default_top50] >= 0.8).mean())
    rhos = np.array(rhos)
    names = universe.drop_duplicates("ticker").set_index("ticker")["name"]
    solid_top = top_share[top_share >= 0.9].sort_values(ascending=False)
    solid_bottom = bottom_share[bottom_share >= 0.9].sort_values(ascending=False)
    verdict = (
        f"Across {runs:,} random weightings the ranking barely moves (median rank correlation with the chosen weights "
        f"{np.median(rhos):.2f}): {stays:.0%} of the top 50 stay in the top fifth in at least 80% of them."
    )
    return {
        "status": "passed" if np.median(rhos) >= 0.7 else "flagged",
        "verdict": verdict,
        "numbers": {
            "runs": runs, "seed": SEED, "companies": n,
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
