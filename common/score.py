"""The scoring pipeline: indicators -> ranks -> profile -> category + total scores.

    python run.py score [profile]          -> scores/<profile>/scores.csv

Deterministic - no model calls. Method and reasoning: docs/SCORING.md.

1. load     every `ready` indicator from the catalogs, each company's most recent year
2. rank     percentile rank 0..1 across the universe (or within its GICS sector),
            flipped when lower is better
3. profile  the user chooses which indicators count and how much (profiles/<name>.toml)
4. score    category score = weighted mean of the chosen indicator ranks x 100
            total score    = weighted mean of the category scores
            each only if the parts a company has carry >= min_weight_share of the weight
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from common.config import (
    CATEGORIES,
    DEFAULT_PROFILE,
    MIN_WEIGHT_SHARE,
    PROFILES_DIR,
    ROOT,
    SCORES_DIR,
    UNIVERSE_CSV,
    catalog_path,
    indicator_path,
)

NO_SECTOR = "(no sector)"


# ---------------------------------------------------------------- 1. load
@dataclass
class Dataset:
    """Everything the scoring needs, in memory."""

    universe: pd.DataFrame  # ticker, name, sector - one row per company
    catalog: pd.DataFrame  # ready indicators of all categories, with a `category` column
    values: pd.DataFrame  # wide: index ticker, one column per indicator, latest value
    years: pd.DataFrame  # same shape: the year each value describes
    demo: bool = False


def latest_values(df: pd.DataFrame) -> pd.Series:
    """Most recent value per ticker."""
    return latest(df)["value"]


def latest(df: pd.DataFrame) -> pd.DataFrame:
    """Most recent row per ticker -> index ticker, columns value + year."""
    rows = df.sort_values("year").groupby("ticker").tail(1).set_index("ticker")
    return pd.DataFrame({"value": rows["value"].astype(float), "year": rows["year"].astype(int)})


def load_dataset() -> Dataset:
    """Reads universe, catalogs and all `ready` indicator files from the repo."""
    catalogs = []
    for category in CATEGORIES:
        catalog = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        catalogs.append(catalog[catalog["status"] == "ready"].assign(category=category))
    catalog = pd.concat(catalogs, ignore_index=True)

    values, years = {}, {}
    for _, row in catalog.iterrows():
        rows = latest(pd.read_csv(indicator_path(row["category"], row["indicator_id"])))
        values[row["indicator_id"]], years[row["indicator_id"]] = rows["value"], rows["year"]
    values_df, years_df = pd.DataFrame(values), pd.DataFrame(years)

    if UNIVERSE_CSV.exists():
        universe = pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)[["ticker", "name", "sector"]]
        values_df = values_df.reindex(universe["ticker"])
        years_df = years_df.reindex(universe["ticker"])
    else:  # no universe yet: every ticker that appears in some indicator
        universe = pd.DataFrame({"ticker": sorted(values_df.index), "name": "", "sector": ""})
    values_df.index.name = years_df.index.name = "ticker"
    return Dataset(universe.reset_index(drop=True), catalog, values_df, years_df)


# ---------------------------------------------------------------- 2. rank
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


def rank_table(
    values: pd.DataFrame, catalog: pd.DataFrame, sectors: pd.Series | None = None
) -> pd.DataFrame:
    """Wide table of ranks, same shape as `values`. With `sectors`, companies are ranked
    only against companies of the same sector."""
    ranks = {}
    for _, row in catalog.iterrows():
        ind = row["indicator_id"]
        better = str(row["higher_is_better"]).lower() == "true"
        column = values[ind] if ind in values.columns else pd.Series(dtype=float)
        if sectors is None:
            ranks[ind] = indicator_ranks(column, better)
        else:
            groups = sectors.reindex(column.index).replace("", NO_SECTOR).fillna(NO_SECTOR)
            parts = [indicator_ranks(part, better) for _, part in column.groupby(groups)]
            ranks[ind] = pd.concat(parts) if parts else pd.Series(dtype=float)
    return pd.DataFrame(ranks, index=values.index, columns=list(ranks))


# ---------------------------------------------------------------- 3. profile
@dataclass
class Profile:
    """What one user of the tool cares about. Stored as profiles/<name>.toml."""

    name: str
    description: str = ""
    category_weights: dict[str, float] = field(default_factory=lambda: {c: 1.0 for c in CATEGORIES})
    # indicator_id -> weight. Overrides the catalog weight; 0 switches an indicator off.
    # Indicators not listed keep their catalog weight.
    indicator_weights: dict[str, float] = field(default_factory=dict)
    min_weight_share: float = MIN_WEIGHT_SHARE
    sector_relative: bool = False
    portfolio: dict = field(default_factory=dict)  # phase 3, not used yet

    def weights(self, catalog: pd.DataFrame) -> pd.Series:
        """indicator_id -> weight for every chosen indicator (weight > 0)."""
        w = {
            row["indicator_id"]: float(self.indicator_weights.get(row["indicator_id"], row["weight"]))
            for _, row in catalog.iterrows()
        }
        return pd.Series({k: v for k, v in w.items() if v > 0}, dtype=float)

    def warnings(self, catalog: pd.DataFrame) -> list[str]:
        unknown = sorted(set(self.indicator_weights) - set(catalog["indicator_id"]))
        return [f"profile '{self.name}': indicator '{i}' is not a ready indicator - ignored" for i in unknown]


def profile_from_dict(data: dict, name: str) -> Profile:
    unknown = set(data.get("categories", {})) - set(CATEGORIES)
    if unknown:
        raise ValueError(f"profile '{name}': unknown categories {sorted(unknown)}, allowed {CATEGORIES}")
    categories = {c: float(data.get("categories", {}).get(c, 1.0)) for c in CATEGORIES}
    indicators = {k: float(v) for k, v in data.get("indicators", {}).items()}
    for key, w in {**categories, **indicators}.items():
        if w < 0:
            raise ValueError(f"profile '{name}': weight of '{key}' must be >= 0, got {w}")
    share = float(data.get("min_weight_share", MIN_WEIGHT_SHARE))
    if not 0 <= share <= 1:
        raise ValueError(f"profile '{name}': min_weight_share must be between 0 and 1, got {share}")
    return Profile(
        name=str(data.get("name", name)),
        description=str(data.get("description", "")),
        category_weights=categories,
        indicator_weights=indicators,
        min_weight_share=share,
        sector_relative=bool(data.get("sector_relative", False)),
        portfolio=dict(data.get("portfolio", {})),
    )


def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.toml"


def list_profiles() -> list[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.toml"))


def load_profile(name: str) -> Profile:
    path = profile_path(name)
    if not path.exists():
        raise FileNotFoundError(f"no profile {path.relative_to(ROOT).as_posix()} - have: {list_profiles()}")
    with path.open("rb") as f:
        return profile_from_dict(tomllib.load(f), path.stem)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "profile"


def profile_to_toml(profile: Profile) -> str:
    def value(v) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return f"{v:g}"
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'

    lines = [
        f"name = {value(profile.name)}",
        f"description = {value(profile.description)}",
        f"min_weight_share = {value(profile.min_weight_share)}",
        f"sector_relative = {value(profile.sector_relative)}",
        "",
        "[categories]",
        *(f"{k} = {value(v)}" for k, v in profile.category_weights.items()),
    ]
    if profile.indicator_weights:
        lines += ["", "[indicators]", *(f"{k} = {value(v)}" for k, v in profile.indicator_weights.items())]
    if profile.portfolio:
        lines += ["", "[portfolio]", *(f"{k} = {value(v)}" for k, v in profile.portfolio.items())]
    return "\n".join(lines) + "\n"


def save_profile(profile: Profile, name: str | None = None) -> Path:
    path = profile_path(slugify(name or profile.name))
    PROFILES_DIR.mkdir(exist_ok=True)
    path.write_text(profile_to_toml(profile), encoding="utf-8")
    return path


# ---------------------------------------------------------------- 4. score
def weighted_score(
    parts: pd.DataFrame, weights: pd.Series, min_weight_share: float, decimals: int | None = 1
) -> pd.DataFrame:
    """Weighted mean of `parts` (values 0..1) x 100, per row. Missing parts are skipped,
    not counted as 0. No score if the available parts carry < min_weight_share of the weight."""
    weights = weights[weights > 0].reindex(parts.columns).dropna()
    parts = parts[weights.index]
    if parts.shape[1] == 0:
        nan = pd.Series(float("nan"), index=parts.index)
        return pd.DataFrame({"score": nan, "n_indicators": 0, "weight_share": nan})
    available = parts.notna().mul(weights, axis=1).sum(axis=1)
    weight_share = available / weights.sum()
    score = parts.fillna(0).mul(weights, axis=1).sum(axis=1) / available.where(available > 0) * 100
    score = score.where(weight_share >= min_weight_share)
    return pd.DataFrame(
        {
            "score": score if decimals is None else score.round(decimals),
            "n_indicators": parts.notna().sum(axis=1),
            "weight_share": weight_share.round(2),
        }
    )


@dataclass
class Result:
    table: pd.DataFrame  # one row per company: total_score, <cat>_score, ... sorted best first
    ranks: pd.DataFrame  # wide: ticker x chosen indicator, 0..1
    weights: pd.Series  # indicator_id -> weight of the chosen indicators
    category_weights: pd.Series  # category -> weight, only categories that have chosen indicators


def score_profile(data: Dataset, profile: Profile) -> Result:
    weights = profile.weights(data.catalog)
    chosen = data.catalog[data.catalog["indicator_id"].isin(weights.index)]
    sectors = data.universe.set_index("ticker")["sector"] if profile.sector_relative else None
    ranks = rank_table(data.values, chosen, sectors)

    table = data.universe.set_index("ticker")[["name", "sector"]].copy()
    category_scores = {}
    for category in CATEGORIES:
        ids = chosen.loc[chosen["category"] == category, "indicator_id"]
        part = weighted_score(ranks[list(ids)], weights[list(ids)], profile.min_weight_share, decimals=None)
        category_scores[category] = part["score"]  # unrounded, so the total is exact
        table[f"{category}_score"] = part["score"].round(1)
        table[f"{category}_n_indicators"] = part["n_indicators"]
        table[f"{category}_weight_share"] = part["weight_share"]

    active = {
        c: float(profile.category_weights.get(c, 0))
        for c in CATEGORIES
        if (chosen["category"] == c).any() and profile.category_weights.get(c, 0) > 0
    }
    category_weights = pd.Series(active, dtype=float)
    total = weighted_score(pd.DataFrame(category_scores) / 100, category_weights, profile.min_weight_share)
    table.insert(2, "total_score", total["score"])
    table.insert(3, "total_weight_share", total["weight_share"])
    table.insert(2, "position", table["total_score"].rank(ascending=False, method="min").astype("Int64"))

    table = table.reset_index().sort_values(["total_score", "ticker"], ascending=[False, True], na_position="last")
    return Result(table.reset_index(drop=True), ranks, weights, category_weights)


def explain(data: Dataset, result: Result, ticker: str) -> pd.DataFrame:
    """Why a company has its total score: one row per chosen indicator.
    `points` add up to the total score (when the company has one)."""
    row = result.table.set_index("ticker").loc[ticker]
    cat_scores = pd.Series({c: row[f"{c}_score"] for c in result.category_weights.index}, dtype=float)
    cat_w = result.category_weights[cat_scores.notna()]
    cat_share = cat_w / cat_w.sum() if cat_w.sum() else cat_w

    rows = []
    for _, ind in data.catalog[data.catalog["indicator_id"].isin(result.weights.index)].iterrows():
        cat, iid = ind["category"], ind["indicator_id"]
        same_cat = data.catalog.loc[data.catalog["category"] == cat, "indicator_id"]
        same_cat = [i for i in same_cat if i in result.weights.index]
        present = [i for i in same_cat if pd.notna(result.ranks.at[ticker, i])]
        rank = result.ranks.at[ticker, iid]
        share_in_cat = result.weights[iid] / result.weights[present].sum() if iid in present else 0.0
        rows.append(
            {
                "category": cat,
                "indicator_id": iid,
                "name": ind["name"],
                "value": data.values.at[ticker, iid],
                "unit": ind["unit"],
                "year": data.years.at[ticker, iid],
                "higher_is_better": ind["higher_is_better"] == "true",
                "rank": rank,
                "weight": result.weights[iid],
                "share_in_category": share_in_cat,
                "points": (rank * 100 * share_in_cat * cat_share.get(cat, 0.0)) if pd.notna(rank) else 0.0,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- compatibility + CLI
def score_category(
    catalog: pd.DataFrame,
    indicators: dict[str, pd.DataFrame],
    universe: set[str] | None = None,
    min_weight_share: float = MIN_WEIGHT_SHARE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One category with catalog weights. Returns (scores by ticker, long table of ranks)."""
    ready = catalog[catalog["status"] == "ready"]
    values = pd.DataFrame({ind: latest_values(indicators[ind]) for ind in ready["indicator_id"]})
    if universe is not None:
        values = values[values.index.isin(universe)]
    ranks = rank_table(values, ready)
    scores = weighted_score(ranks, ready.set_index("indicator_id")["weight"].astype(float), min_weight_share)
    long = ranks.rename_axis("ticker").reset_index().melt(
        id_vars="ticker", var_name="indicator_id", value_name="rank"
    ).dropna()
    return scores, long


def build_scores(profile_name: str = DEFAULT_PROFILE) -> pd.DataFrame:
    profile = load_profile(profile_name)
    data = load_dataset()
    for msg in profile.warnings(data.catalog):
        print(f"  WARN {msg}")
    result = score_profile(data, profile)

    print(f"  profile '{profile_name}': {len(result.weights)} indicators chosen")
    for category in CATEGORIES:
        n = int((data.catalog.loc[data.catalog["indicator_id"].isin(result.weights.index), "category"] == category).sum())
        scored = int(result.table[f"{category}_score"].notna().sum())
        print(f"  {category:<14} {n} indicators, {scored} companies scored")
    print(f"  {'total':<14} {int(result.table['total_score'].notna().sum())} companies scored")

    out = SCORES_DIR / profile_name
    out.mkdir(parents=True, exist_ok=True)
    result.table.to_csv(out / "scores.csv", index=False, lineterminator="\n")
    long = result.ranks.rename_axis("ticker").reset_index().melt(
        id_vars="ticker", var_name="indicator_id", value_name="rank"
    ).dropna()
    long.to_csv(out / "indicator_ranks.csv", index=False, lineterminator="\n")
    print(f"  wrote {(out / 'scores.csv').relative_to(ROOT).as_posix()}")
    return result.table


if __name__ == "__main__":
    build_scores()
