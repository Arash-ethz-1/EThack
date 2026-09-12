"""Phase 3 - turns a profile's scores into portfolio weights.

    python run.py portfolio [profile]      -> scores/<profile>/portfolio.csv

Deterministic - no model calls, like the scores. Method (proposal by Florian,
docs/superpowers/plans/2026-09-12-portfolio-allocation.md):

1. benchmark    equal weight over the universe (market-cap weights once they exist)
2. standardise  z-score of total_score; a company WITHOUT a score gets z = 0 (neutral)
3. tilt         w_i ~ benchmark_i * exp(tilt_strength * z_i)      (method = "tilt")
   or exclude   drop the worst X% of scored companies            (method = "exclude")
4. sector       rescale each GICS sector back to its benchmark weight (sector_neutral)
5. cap          no company above max_weight; the excess is spread over the others

Why a tilt and not a stock pick: every company stays investable, weights stay positive
(no shorting), strength 0 is exactly the benchmark, so one dial goes from index-hugging
to concentrated. Why sector-neutral by default: our scores differ a lot by sector
(Financials score high on the environmental indicators because they own no mines), and
a sustainability fund should reward the better company in each sector, not make a
sector bet. Why unscored companies stay at benchmark: a data gap is our problem, not
evidence about the company.

Settings live under [portfolio] in profiles/<name>.toml; missing ones use DEFAULTS.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.config import CATEGORIES, DEFAULT_PROFILE, ROOT, SCORES_DIR
from common.score import Profile

OUTPUT_COLUMNS = ["ticker", "weight", "reason"]  # weights sum to 1

DEFAULTS = {
    "method": "tilt",
    "tilt_strength": 0.6,
    "exclude_bottom_pct": 0.1,
    "max_weight": 0.05,
    "sector_neutral": True,
}
SETTINGS = {
    "method": "tilt | exclude",
    "tilt_strength": "tilt: weight x exp(strength x z-score); 0 = benchmark, 0.6 = one std better -> 1.8x weight",
    "exclude_bottom_pct": "exclude: drop the worst share of scored companies, e.g. 0.1",
    "max_weight": "cap per company, e.g. 0.05",
    "sector_neutral": "true = every sector keeps its benchmark weight",
}
PLANNED_SETTINGS = SETTINGS  # name the dashboard imports

MAX_EXPONENT = 20.0  # exp(20) ~ 4.9e8; beyond this float64 loses all resolution


# ---------------------------------------------------------------- building blocks
def benchmark_weights(scores: pd.DataFrame, marketcaps: pd.Series | None = None) -> pd.Series:
    """Starting weights before any tilt. Equal weight unless market caps are supplied.
    A company without a market cap gets the median cap rather than being dropped."""
    tickers = scores["ticker"].astype(str)
    if marketcaps is None or marketcaps.dropna().empty:
        return pd.Series(1.0 / len(tickers), index=tickers.to_numpy())
    caps = marketcaps.reindex(tickers).astype(float)
    caps = caps.fillna(caps.median())
    return caps / caps.sum()


def score_z(scores: pd.DataFrame, column: str = "total_score") -> pd.Series:
    """Standardised score per ticker (mean 0, std 1 over scored companies).
    A company without a score gets 0.0 - neutral, so the tilt leaves its weight alone."""
    values = pd.Series(scores[column].to_numpy(), index=scores["ticker"].astype(str).to_numpy(), dtype=float)
    scored = values.dropna()
    spread = scored.std(ddof=0) if len(scored) else 0.0
    if not spread:
        return pd.Series(0.0, index=values.index)
    return ((values - scored.mean()) / spread).fillna(0.0)


def tilt(benchmark: pd.Series, z: pd.Series, strength: float) -> pd.Series:
    """benchmark_i * exp(strength * z_i), renormalised. Strength 0 returns the benchmark."""
    exponent = (strength * z.reindex(benchmark.index).fillna(0.0)).clip(-MAX_EXPONENT, MAX_EXPONENT)
    weights = benchmark * np.exp(exponent)
    return weights / weights.sum()


def exclude_worst(benchmark: pd.Series, scores: pd.DataFrame, bottom_pct: float) -> pd.Series:
    """Drop the worst `bottom_pct` of SCORED companies, keep everything else at benchmark.
    Unscored companies are never excluded - missing data is not a reason to divest."""
    values = pd.Series(scores["total_score"].to_numpy(), index=scores["ticker"].astype(str).to_numpy(), dtype=float)
    scored = values.dropna()
    n_drop = int(len(scored) * bottom_pct)
    out = benchmark.copy()
    if n_drop > 0:
        # ties at the cut-off: ticker order decides, so the result is deterministic
        worst = scored.sort_index().sort_values(kind="stable").index[:n_drop]
        out.loc[worst] = 0.0
    if out.sum() <= 0:
        raise ValueError(f"exclude_bottom_pct {bottom_pct} excluded every company")
    return out / out.sum()


def sector_neutralise(weights: pd.Series, benchmark: pd.Series, sectors: pd.Series) -> pd.Series:
    """Rescale each sector so its total equals the benchmark's; order inside a sector stays."""
    sec = sectors.reindex(weights.index).fillna("(no sector)").replace("", "(no sector)")
    out = weights.copy()
    for _, members in sec.groupby(sec).groups.items():
        target = benchmark.reindex(members).sum()
        current = weights.reindex(members).sum()
        out.loc[members] = weights.loc[members] * (target / current) if current > 0 else benchmark.loc[members]
    return out / out.sum()


def apply_cap(weights: pd.Series, max_weight: float, max_rounds: int = 100) -> pd.Series:
    """Cap each weight and spread the excess over the uncapped names, repeatedly
    (spreading can push another name over the cap)."""
    held = weights[weights > 0]
    if max_weight <= 0 or max_weight * len(held) < 1 - 1e-12:
        raise ValueError(
            f"max_weight {max_weight} cannot hold {len(held)} companies - needs at least {1 / max(len(held), 1):.4f}"
        )
    out = weights / weights.sum()
    for _ in range(max_rounds):
        over = out > max_weight + 1e-12
        if not over.any():
            break
        excess = (out[over] - max_weight).sum()
        out[over] = max_weight
        free = (~over) & (out > 0) & (out < max_weight)
        if out[free].sum() <= 0:
            break
        out[free] += excess * out[free] / out[free].sum()
    return out


def settings_for(profile: Profile) -> dict:
    """DEFAULTS overridden by the profile's [portfolio] block, validated."""
    given = dict(getattr(profile, "portfolio", None) or {})
    unknown = sorted(set(given) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"profile '{profile.name}': unknown [portfolio] settings {unknown}, allowed {sorted(DEFAULTS)}")
    s = {**DEFAULTS, **given}
    s["tilt_strength"] = float(s["tilt_strength"])
    s["exclude_bottom_pct"] = float(s["exclude_bottom_pct"])
    s["max_weight"] = float(s["max_weight"])
    s["sector_neutral"] = str(s["sector_neutral"]).lower() == "true"
    if s["method"] not in ("tilt", "exclude"):
        raise ValueError(f"profile '{profile.name}': [portfolio] method must be 'tilt' or 'exclude', got {s['method']!r}")
    if s["tilt_strength"] < 0:
        raise ValueError(f"profile '{profile.name}': tilt_strength must be >= 0")
    if not 0 <= s["exclude_bottom_pct"] < 1:
        raise ValueError(f"profile '{profile.name}': exclude_bottom_pct must be in [0, 1)")
    if not 0 < s["max_weight"] <= 1:
        raise ValueError(f"profile '{profile.name}': max_weight must be in (0, 1]")
    return s


# ---------------------------------------------------------------- allocate
def allocate(scores: pd.DataFrame, profile: Profile, fund_usd: float = 1e9) -> pd.DataFrame:
    """scores: Result.table from common.score.score_profile. Returns OUTPUT_COLUMNS,
    one row per company, weights sum to 1, largest first. `fund_usd` is only used by
    callers that turn weights into dollars (weight x fund_usd)."""
    s = settings_for(profile)
    tickers = scores["ticker"].astype(str).to_numpy()
    sectors = pd.Series(scores["sector"].to_numpy(), index=tickers)
    total = pd.Series(scores["total_score"].to_numpy(), index=tickers, dtype=float)

    bench = benchmark_weights(scores)
    z = score_z(scores)
    if s["method"] == "exclude":
        weights = exclude_worst(bench, scores, s["exclude_bottom_pct"])
        how = f"bottom {s['exclude_bottom_pct']:.0%} excluded"
    else:
        weights = tilt(bench, z, s["tilt_strength"])
        how = f"tilt {s['tilt_strength']:g}"
    if s["sector_neutral"]:
        weights = sector_neutralise(weights, bench, sectors)
        how += ", sector-neutral"
    weights = apply_cap(weights, s["max_weight"])

    reasons = []
    for t in weights.index:
        rel = weights[t] / bench[t]
        if pd.isna(total[t]):
            reasons.append(f"no score - not enough data, held near benchmark ({rel:.2f}x)")
        elif weights[t] == 0:
            reasons.append(f"score {total[t]:.1f} - excluded ({how})")
        else:
            capped = " capped" if weights[t] >= s["max_weight"] - 1e-12 else ""
            reasons.append(f"score {total[t]:.1f}, z {z[t]:+.2f} -> {rel:.2f}x benchmark ({how}{capped})")
    out = pd.DataFrame({"ticker": weights.index, "weight": weights.to_numpy(), "reason": reasons})
    return out.sort_values(["weight", "ticker"], ascending=[False, True]).reset_index(drop=True)[OUTPUT_COLUMNS]


def summary(scores: pd.DataFrame, portfolio: pd.DataFrame) -> dict:
    """How the portfolio differs from the equal-weight benchmark, in numbers."""
    table = scores.set_index(scores["ticker"].astype(str))
    w = portfolio.set_index("ticker")["weight"].reindex(table.index).fillna(0.0)
    b = benchmark_weights(scores)

    def weighted(col: str, weights: pd.Series) -> float:
        v = table[col].astype(float)
        m = v.notna()
        return float((v[m] * weights[m]).sum() / weights[m].sum()) if weights[m].sum() else float("nan")

    cols = ["total_score"] + [f"{c}_score" for c in CATEGORIES if f"{c}_score" in table.columns]
    sector_w = pd.DataFrame({"portfolio": w.groupby(table["sector"]).sum(), "benchmark": b.groupby(table["sector"]).sum()})
    return {
        "holdings": int((w > 0).sum()),
        "max_weight": float(w.max()),
        "top10_weight": float(w.nlargest(10).sum()),
        "active_share": float(0.5 * (w - b).abs().sum()),
        "unscored_weight": float(w[table["total_score"].isna()].sum()),
        "scores": {c: {"portfolio": weighted(c, w), "benchmark": weighted(c, b)} for c in cols},
        "sector_weights": sector_w,
    }


def build_portfolio(profile_name: str = DEFAULT_PROFILE, fund_usd: float = 1e9) -> pd.DataFrame:
    """Scores the profile, allocates, writes scores/<profile>/portfolio.csv, prints a summary."""
    from common.score import build_scores, load_profile

    profile = load_profile(profile_name)
    scores = build_scores(profile_name)
    portfolio = allocate(scores, profile, fund_usd)
    table = scores.set_index("ticker")
    out = portfolio.assign(
        usd=(portfolio["weight"] * fund_usd).round(0),
        name=portfolio["ticker"].map(table["name"]),
        sector=portfolio["ticker"].map(table["sector"]),
        total_score=portfolio["ticker"].map(table["total_score"]),
    )[["ticker", "name", "sector", "total_score", "weight", "usd", "reason"]]
    path = SCORES_DIR / profile_name / "portfolio.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, lineterminator="\n")

    s = summary(scores, portfolio)
    print(f"  portfolio '{profile_name}': {settings_for(profile)}")
    print(f"  {s['holdings']} holdings, max weight {s['max_weight']:.2%}, top 10 = {s['top10_weight']:.1%}, "
          f"active share {s['active_share']:.1%}, unscored companies {s['unscored_weight']:.1%}")
    for col, v in s["scores"].items():
        print(f"  {col:<22} portfolio {v['portfolio']:5.1f}   equal-weight benchmark {v['benchmark']:5.1f}")
    print(f"  wrote {path.relative_to(ROOT).as_posix()} (fund {fund_usd:,.0f} USD)")
    return out
