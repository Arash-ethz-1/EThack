"""Turns ready indicators into one 0-100 score per category. Deterministic - no model calls.

    python run.py score

Method (details and reasoning in docs/SCORING.md):
1. per indicator, take each company's most recent year
2. percentile-rank across the universe -> 0..1, flipped when lower is better
3. category score = weighted mean of the available ranks x 100,
   only if the available indicators carry >= MIN_WEIGHT_SHARE of the category weight
"""

from __future__ import annotations

import pandas as pd

from common.config import (
    CATEGORIES,
    MIN_WEIGHT_SHARE,
    ROOT,
    SCORES_DIR,
    UNIVERSE_CSV,
    catalog_path,
    indicator_path,
)


def latest_values(df: pd.DataFrame) -> pd.Series:
    """Most recent value per ticker."""
    latest = df.sort_values("year").groupby("ticker").tail(1)
    return latest.set_index("ticker")["value"].astype(float)


def indicator_ranks(values: pd.Series, higher_is_better: bool) -> pd.Series:
    """Percentile rank in [0, 1]: 1 = best company, 0 = worst. Ties share the average rank."""
    values = values.dropna()
    n = len(values)
    if n == 0:
        return values
    if n == 1:
        return pd.Series(0.5, index=values.index)
    ranks = (values.rank(method="average") - 1) / (n - 1)
    return ranks if higher_is_better else 1 - ranks


def score_category(
    catalog: pd.DataFrame,
    indicators: dict[str, pd.DataFrame],
    universe: set[str] | None = None,
    min_weight_share: float = MIN_WEIGHT_SHARE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (scores indexed by ticker, long table of per-indicator ranks)."""
    ready = catalog[catalog["status"] == "ready"]
    rank_cols, weights = {}, {}
    for _, row in ready.iterrows():
        ind = row["indicator_id"]
        values = latest_values(indicators[ind])
        if universe is not None:
            values = values[values.index.isin(universe)]
        rank_cols[ind] = indicator_ranks(values, str(row["higher_is_better"]).lower() == "true")
        weights[ind] = float(row["weight"])

    if not rank_cols:
        empty = pd.DataFrame(columns=["score", "n_indicators", "weight_share"])
        return empty, pd.DataFrame(columns=["ticker", "indicator_id", "rank"])

    ranks = pd.DataFrame(rank_cols)
    w = pd.Series(weights)
    available = ranks.notna().mul(w, axis=1)
    weight_share = available.sum(axis=1) / w.sum()
    score = ranks.fillna(0).mul(w, axis=1).sum(axis=1) / available.sum(axis=1) * 100

    out = pd.DataFrame(
        {
            "score": score.where(weight_share >= min_weight_share).round(1),
            "n_indicators": ranks.notna().sum(axis=1),
            "weight_share": weight_share.round(2),
        }
    )
    long = ranks.rename_axis("ticker").reset_index().melt(
        id_vars="ticker", var_name="indicator_id", value_name="rank"
    ).dropna()
    return out, long


def build_scores() -> pd.DataFrame:
    universe_df = pd.read_csv(UNIVERSE_CSV, dtype=str) if UNIVERSE_CSV.exists() else None
    universe = set(universe_df["ticker"]) if universe_df is not None else None

    frames, longs = [], []
    for category in CATEGORIES:
        catalog = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        ready = catalog.loc[catalog["status"] == "ready", "indicator_id"]
        indicators = {ind: pd.read_csv(indicator_path(category, ind)) for ind in ready}
        scores, long = score_category(catalog, indicators, universe)
        print(f"  {category:<14} {len(ready)} ready indicators, {scores['score'].notna().sum()} companies scored")
        frames.append(scores.add_prefix(f"{category}_"))
        longs.append(long.assign(category=category))

    table = pd.concat(frames, axis=1)
    table.index.name = "ticker"
    table = table.reset_index()
    if universe_df is not None:
        table = universe_df[["ticker", "name", "sector"]].merge(table, on="ticker", how="left")

    SCORES_DIR.mkdir(exist_ok=True)
    table.to_csv(SCORES_DIR / "category_scores.csv", index=False, lineterminator="\n")
    pd.concat(longs).to_csv(SCORES_DIR / "indicator_ranks.csv", index=False, lineterminator="\n")
    print(f"  wrote {(SCORES_DIR / 'category_scores.csv').relative_to(ROOT).as_posix()}")
    return table


if __name__ == "__main__":
    build_scores()
