"""Phase 3 - turns a profile's scores into portfolio weights.

    python run.py portfolio [profile]      -> scores/<profile>/portfolio.csv

Deterministic - no model calls, like the scores. Method (proposal by Florian,
docs/superpowers/plans/2026-09-12-portfolio-allocation.md, decisions in docs/PLAN.md):

0. companies    one row per company (CIK): share classes are ONE holding (see SHARE_CLASS_RULE)
1. benchmark    market-cap weights (shares outstanding x price, portfolio/marketdata.py) or
                equal weight. A company without a market cap is not in the cap benchmark.
2. exclusions   GICS sub-industries the profile rules out get weight 0 (a policy, not a score)
3. standardise  z-score of total_score over the investable companies; no score -> z = 0
4. tilt         w_i ~ benchmark_i * exp(tilt_strength * z_i)      (method = "tilt")
   or exclude   drop the worst X% of scored companies            (method = "exclude")
5. sector       rescale each GICS sector back to its benchmark weight AFTER exclusions
                (otherwise an emptied sector would fall back to the benchmark and re-admit
                the excluded companies)
6. cap          no company above max_weight; the excess stays inside its sector when it can

Why a tilt and not a stock pick: every company stays investable, weights stay positive
(no shorting), strength 0 is exactly the benchmark, so one dial goes from index-hugging
to concentrated. Why sector-neutral by default: a sustainability fund should reward the
better company in each sector, not make a sector bet. Why unscored companies stay at
benchmark: a data gap is our problem, not evidence about the company.

Settings live under [portfolio] in profiles/<name>.toml; missing ones use DEFAULTS.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from common.config import CATEGORIES, DEFAULT_PROFILE, ROOT, SCORES_DIR, UNIVERSE_CSV
from common.score import Profile

# one row per company; weights sum to 1
OUTPUT_COLUMNS = ["ticker", "weight", "benchmark_weight", "active_weight", "status", "reason"]
STATUSES = {
    "held": "held",
    "excluded_policy": "excluded by a sub-industry rule",
    "excluded_score": "excluded for a low score",
    "no_market_cap": "no market cap - not in the benchmark",
}

DEFAULTS = {
    "method": "tilt",
    "tilt_strength": 0.6,
    "exclude_bottom_pct": 0.1,
    "max_weight": 0.05,
    "sector_neutral": True,
    "benchmark": "equal",  # "cap" once portfolio/raw market data is built and coverage checked
    "exclude_sub_industries": [],
}
SETTINGS = {
    "method": "tilt | exclude",
    "tilt_strength": "tilt: weight x exp(strength x z-score); 0 = benchmark, 0.6 = one std better -> 1.8x weight",
    "exclude_bottom_pct": "exclude: drop the worst share of scored companies, e.g. 0.1",
    "max_weight": "cap per company, e.g. 0.05",
    "sector_neutral": "true = every sector keeps its benchmark weight (after exclusions)",
    "benchmark": "cap = market-cap weights (like the real S&P 500) | equal = every company the same",
    "exclude_sub_industries": "GICS sub-industries with weight 0, exact names from universe/sp500.csv",
}
PLANNED_SETTINGS = SETTINGS  # name the dashboard imports

MAX_EXPONENT = 20.0  # exp(20) ~ 4.9e8; beyond this float64 loses all resolution
EPS = 1e-12

# Share classes of one company (same SEC CIK) are one holding - otherwise Alphabet would
# get its benchmark weight twice. The fund holds the class that carries the VOTE, because
# a sustainability fund engages through proxy voting (source: each company's 10-K cover
# page / charter). The company's market cap still counts every listed class.
PREFERRED_CLASS = {
    "GOOGL": "Alphabet Class A - 1 vote per share (GOOG, Class C, has none)",
    "FOX": "Fox Class B - the voting class (FOXA, Class A, is non-voting)",
    "NWS": "News Corp Class B - the voting class (NWSA, Class A, is non-voting)",
}
SHARE_CLASS_RULE = (
    "one holding per company (SEC CIK): the voting share class from PREFERRED_CLASS, "
    "otherwise the alphabetically first ticker; the company's weight counts once"
)


# ---------------------------------------------------------------- companies
def companies(scores: pd.DataFrame, universe: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per company. Adds cik, sub_industry and `other_classes` to the score table.
    Without a universe (or cik column) every ticker is its own company."""
    table = scores.copy()
    table["ticker"] = table["ticker"].astype(str)
    if universe is not None:
        info = universe.set_index(universe["ticker"].astype(str))
        for col in ("cik", "sub_industry", "sector", "name"):
            if col in info.columns and col not in table.columns:
                table[col] = table["ticker"].map(info[col])
    if "cik" not in table.columns:
        table["cik"] = table["ticker"]
    table["cik"] = table["cik"].fillna(table["ticker"]).astype(str)
    if "sub_industry" not in table.columns:
        table["sub_industry"] = ""
    table["sub_industry"] = table["sub_industry"].fillna("")

    def holding(tickers: list[str]) -> str:
        preferred = [t for t in tickers if t in PREFERRED_CLASS]
        return preferred[0] if preferred else sorted(tickers)[0]

    groups = table.groupby("cik")["ticker"].apply(list)
    keep = {cik: holding(ts) for cik, ts in groups.items()}
    others = {cik: ", ".join(sorted(t for t in ts if t != keep[cik])) for cik, ts in groups.items()}
    out = table[table["ticker"] == table["cik"].map(keep)].copy()
    out["other_classes"] = out["cik"].map(others)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------- building blocks
def benchmark_weights(scores: pd.DataFrame, marketcaps: pd.Series | None = None) -> pd.Series:
    """Starting weights per ticker. Equal weight unless market caps (by ticker) are supplied.
    With market caps, a company without one gets weight 0 - it is not estimated."""
    tickers = scores["ticker"].astype(str)
    if marketcaps is None:
        return pd.Series(1.0 / len(tickers), index=tickers.to_numpy())
    caps = marketcaps.reindex(tickers.to_numpy()).astype(float)
    if caps.dropna().empty or caps.sum() <= 0:
        raise ValueError("no company has a market cap - cannot build a cap-weighted benchmark")
    return (caps.fillna(0.0) / caps.sum()).rename(None)


def score_z(scores: pd.DataFrame, column: str = "total_score", investable: pd.Series | None = None) -> pd.Series:
    """Standardised score per ticker (mean 0, std 1 over scored, investable companies).
    A company without a score gets 0.0 - neutral, so the tilt leaves its weight alone."""
    values = pd.Series(scores[column].to_numpy(), index=scores["ticker"].astype(str).to_numpy(), dtype=float)
    pool = values if investable is None else values[investable.reindex(values.index).fillna(False).astype(bool)]
    scored = pool.dropna()
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
    """Drop the worst `bottom_pct` of SCORED companies that are in the benchmark, keep everything
    else at benchmark. Unscored companies are never excluded - missing data is not a reason to divest."""
    values = pd.Series(scores["total_score"].to_numpy(), index=scores["ticker"].astype(str).to_numpy(), dtype=float)
    scored = values[benchmark.reindex(values.index).fillna(0) > 0].dropna()
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
    """Rescale each sector so its total equals the benchmark's; order inside a sector stays.
    Pass the benchmark AFTER exclusions: a sector whose benchmark is 0 stays at 0."""
    sec = sectors.reindex(weights.index).fillna("(no sector)").replace("", "(no sector)")
    out = weights.copy()
    for _, members in sec.groupby(sec).groups.items():
        target = benchmark.reindex(members).fillna(0).sum()
        current = weights.reindex(members).sum()
        out.loc[members] = weights.loc[members] * (target / current) if current > 0 else benchmark.reindex(members).fillna(0)
    return out / out.sum()


def _waterfill(w: pd.Series, total: float, cap: float) -> pd.Series:
    """Spread `total` over w's positive names proportional to w, nobody above `cap`.
    Returns weights summing to min(total, cap x names)."""
    out = pd.Series(0.0, index=w.index)
    free = w[w > 0].index
    remaining = total
    while len(free) and remaining > EPS:
        scaled = w[free] * remaining / w[free].sum()
        over = scaled[scaled > cap + EPS].index
        if not len(over):
            out[free] = scaled
            break
        out[over] = cap
        remaining -= cap * len(over)
        free = free.difference(over)
    return out


def apply_cap(weights: pd.Series, max_weight: float, groups: pd.Series | None = None) -> pd.Series:
    """No weight above max_weight, total stays 1. With `groups` (sectors) the excess is first
    spread inside the same group, so sector totals stay where they were; only a group that
    cannot hold its total under the cap spills the rest over everyone else."""
    held = weights[weights > 0]
    if max_weight <= 0 or max_weight * len(held) < 1 - 1e-9:
        raise ValueError(
            f"max_weight {max_weight} cannot hold {len(held)} companies - needs at least {1 / max(len(held), 1):.4f}"
        )
    w = weights / weights.sum()
    if groups is None:
        return _waterfill(w, 1.0, max_weight)
    g = groups.reindex(w.index).fillna("(no sector)")
    out = pd.Series(0.0, index=w.index)
    for _, members in g.groupby(g).groups.items():
        part = w.loc[members]
        out.loc[members] = _waterfill(part, part.sum(), max_weight)
    spill = 1.0 - out.sum()
    rounds = 0
    while spill > 1e-12 and rounds < len(w) + 1:
        room = (max_weight - out).clip(lower=0)
        takers = w[(w > 0) & (room > EPS)].index
        if not len(takers):
            break
        add = w[takers] * spill / w[takers].sum()
        add = np.minimum(add, room[takers])
        out[takers] += add
        spill = 1.0 - out.sum()
        rounds += 1
    return out


def settings_for(profile: Profile, overrides: dict | None = None, sub_industries: set[str] | None = None) -> dict:
    """DEFAULTS <- the profile's [portfolio] block <- overrides (dashboard), validated."""
    given = {**dict(getattr(profile, "portfolio", None) or {}), **dict(overrides or {})}
    unknown = sorted(set(given) - set(DEFAULTS))
    if unknown:
        raise ValueError(f"profile '{profile.name}': unknown [portfolio] settings {unknown}, allowed {sorted(DEFAULTS)}")
    s = {**DEFAULTS, **given}
    s["tilt_strength"] = float(s["tilt_strength"])
    s["exclude_bottom_pct"] = float(s["exclude_bottom_pct"])
    s["max_weight"] = float(s["max_weight"])
    s["sector_neutral"] = str(s["sector_neutral"]).lower() == "true"
    if isinstance(s["exclude_sub_industries"], str):
        s["exclude_sub_industries"] = [s["exclude_sub_industries"]]
    s["exclude_sub_industries"] = sorted({str(x) for x in s["exclude_sub_industries"]})
    if s["method"] not in ("tilt", "exclude"):
        raise ValueError(f"profile '{profile.name}': [portfolio] method must be 'tilt' or 'exclude', got {s['method']!r}")
    if s["benchmark"] not in ("cap", "equal"):
        raise ValueError(f"profile '{profile.name}': [portfolio] benchmark must be 'cap' or 'equal', got {s['benchmark']!r}")
    if s["tilt_strength"] < 0:
        raise ValueError(f"profile '{profile.name}': tilt_strength must be >= 0")
    if not 0 <= s["exclude_bottom_pct"] < 1:
        raise ValueError(f"profile '{profile.name}': exclude_bottom_pct must be in [0, 1)")
    if not 0 < s["max_weight"] <= 1:
        raise ValueError(f"profile '{profile.name}': max_weight must be in (0, 1]")
    if sub_industries is not None:
        typos = [x for x in s["exclude_sub_industries"] if x not in sub_industries]
        if typos:
            raise ValueError(f"profile '{profile.name}': exclude_sub_industries {typos} are not GICS sub-industries in universe/sp500.csv")
    return s


# ---------------------------------------------------------------- allocate
def allocate(
    scores: pd.DataFrame,
    profile: Profile,
    universe: pd.DataFrame | None = None,
    marketcaps: pd.Series | None = None,
    overrides: dict | None = None,
) -> pd.DataFrame:
    """scores: Result.table from common.score.score_profile. universe: universe/sp500.csv
    (cik + sub_industry). marketcaps: USD by CIK (only needed for benchmark = "cap").
    Returns OUTPUT_COLUMNS, one row per company, weights sum to 1, largest first."""
    subs = set(universe["sub_industry"]) if universe is not None and "sub_industry" in universe.columns else None
    s = settings_for(profile, overrides, subs)
    table = companies(scores, universe)
    idx = table["ticker"].to_numpy()
    sectors = pd.Series(table["sector"].to_numpy(), index=idx)
    total = pd.Series(table["total_score"].to_numpy(), index=idx, dtype=float)

    if s["benchmark"] == "cap":
        if marketcaps is None:
            raise ValueError("benchmark = 'cap' needs market caps - run `python portfolio/marketdata.py` or set benchmark = 'equal'")
        caps = pd.Series(table["cik"].map(marketcaps).to_numpy(), index=idx, dtype=float)
        bench = benchmark_weights(table, caps)
    else:
        caps = None
        bench = benchmark_weights(table)
    no_cap = bench <= 0

    policy = pd.Series(table["sub_industry"].isin(s["exclude_sub_industries"]).to_numpy(), index=idx)
    eligible = bench.where(~policy, 0.0)
    if eligible.sum() <= 0:
        raise ValueError("the sub-industry exclusions remove every company")
    eligible = eligible / eligible.sum()

    z = score_z(table, investable=eligible > 0)
    if s["method"] == "exclude":
        weights = exclude_worst(eligible, table, s["exclude_bottom_pct"])
        how = f"bottom {s['exclude_bottom_pct']:.0%} excluded"
    else:
        weights = tilt(eligible, z, s["tilt_strength"])
        how = f"tilt {s['tilt_strength']:g}"
    if s["sector_neutral"]:
        weights = sector_neutralise(weights, eligible, sectors)
        how += ", sector-neutral"
    weights = apply_cap(weights, s["max_weight"], sectors if s["sector_neutral"] else None)

    status, reasons = [], []
    others = pd.Series(table["other_classes"].to_numpy(), index=idx)
    subs_of = pd.Series(table["sub_industry"].to_numpy(), index=idx)
    for t in idx:
        classes = f"; one holding for all share classes (also {others[t]})" if others[t] else ""
        if no_cap[t]:
            status.append("no_market_cap")
            reasons.append("no market cap on record - not in the cap-weighted benchmark, not held" + classes)
        elif policy[t]:
            status.append("excluded_policy")
            reasons.append(f"excluded: GICS sub-industry {subs_of[t]} (a classification, not a revenue test)" + classes)
        elif weights[t] <= 0:
            status.append("excluded_score")
            reasons.append(f"score {total[t]:.1f} - excluded ({how})" + classes)
        else:
            rel = weights[t] / eligible[t] if eligible[t] > 0 else float("nan")
            capped = ", capped" if weights[t] >= s["max_weight"] - 1e-9 else ""
            status.append("held")
            if pd.isna(total[t]):
                reasons.append(f"no score - not enough data, held near benchmark ({rel:.2f}x){classes}")
            else:
                reasons.append(f"score {total[t]:.1f}, z {z[t]:+.2f} -> {rel:.2f}x benchmark ({how}{capped}){classes}")
    out = pd.DataFrame({
        "ticker": idx,
        "weight": weights.reindex(idx).to_numpy(),
        "benchmark_weight": bench.reindex(idx).to_numpy(),
        "status": status,
        "reason": reasons,
    })
    out["active_weight"] = out["weight"] - out["benchmark_weight"]
    return out.sort_values(["weight", "benchmark_weight", "ticker"], ascending=[False, False, True]).reset_index(drop=True)[OUTPUT_COLUMNS]


def summary(scores: pd.DataFrame, portfolio: pd.DataFrame, universe: pd.DataFrame | None = None, top: int = 10) -> dict:
    """Our fund vs the benchmark, in numbers. The benchmark is the one BEFORE exclusions -
    the index the fund is compared against."""
    table = companies(scores, universe).set_index("ticker")
    p = portfolio.set_index("ticker")
    w = p["weight"].reindex(table.index).fillna(0.0)
    b = p["benchmark_weight"].reindex(table.index).fillna(0.0)

    def weighted(col: str, weights: pd.Series) -> dict:
        v = table[col].astype(float)
        m = v.notna() & (weights > 0)
        share = float(weights[m].sum() / weights.sum()) if weights.sum() else 0.0
        value = float((v[m] * weights[m]).sum() / weights[m].sum()) if weights[m].sum() else None
        return {"value": value, "weight_with_score": share}

    cols = ["total_score"] + [f"{c}_score" for c in CATEGORIES if f"{c}_score" in table.columns]
    score_rows = {}
    for c in cols:
        fw, bw = weighted(c, w), weighted(c, b)
        score_rows[c] = {"portfolio": fw["value"], "benchmark": bw["value"],
                         "portfolio_weight_with_score": fw["weight_with_score"], "benchmark_weight_with_score": bw["weight_with_score"]}

    sec = pd.DataFrame({"portfolio": w.groupby(table["sector"]).sum(), "benchmark": b.groupby(table["sector"]).sum()})
    sec = sec.assign(active=sec["portfolio"] - sec["benchmark"]).sort_values("benchmark", ascending=False)

    def rows(index) -> list[dict]:
        return [{
            "ticker": t, "name": table.at[t, "name"] if "name" in table.columns else "", "sector": table.at[t, "sector"],
            "total_score": table.at[t, "total_score"], "weight": float(w[t]), "benchmark_weight": float(b[t]),
            "active_weight": float(w[t] - b[t]), "status": p.at[t, "status"], "reason": p.at[t, "reason"],
        } for t in index]

    active = (w - b)
    status = p["status"].value_counts()
    climate = climate_metrics(table.index, w, b)
    return {
        "holdings": int((w > 0).sum()),
        "companies": int(len(table)),
        "excluded_policy": int(status.get("excluded_policy", 0)),
        "excluded_score": int(status.get("excluded_score", 0)),
        "no_market_cap": int(status.get("no_market_cap", 0)),
        "max_weight": float(w.max()),
        "top10_weight": float(w.nlargest(10).sum()),
        "benchmark_top10_weight": float(b.nlargest(10).sum()),
        "active_share": float(0.5 * active.abs().sum()),
        "unscored_weight": float(w[table["total_score"].isna()].sum()),
        "scores": score_rows,
        "sector_weights": sec,
        "overweights": rows(active[active > 0].sort_values(ascending=False).index[:top]),
        "underweights": rows(active[active < 0].sort_values().index[:top]),
        "largest": rows(w[w > 0].sort_values(ascending=False).index[:top]),
        "excluded": rows(p.index[p["status"] == "excluded_policy"]),
        "climate": climate,
    }


def climate_metrics(tickers: pd.Index, w: pd.Series, b: pd.Series) -> dict:
    """The net-zero answer in two standard numbers, fund vs benchmark - weighted averages of
    raw indicator values, not scores:
    - WACI, weighted average carbon intensity (TCFD): sum of weight x tCO2e per $M revenue
      (ghg_intensity, latest year), over the weight that has a value
    - share of weight in companies with a validated science-based target (sbti_climate_target
      >= 2: a near-term target set, 2 = well-below 2C, 3 = 1.5C, 4 = net-zero validated)"""
    from common.config import indicator_path

    def latest(category: str, indicator_id: str) -> pd.Series:
        path = indicator_path(category, indicator_id)
        if not path.exists():
            return pd.Series(dtype=float)
        df = pd.read_csv(path)
        return df.sort_values("year").groupby("ticker")["value"].last().reindex(tickers)

    ghg, sbti = latest("environmental", "ghg_intensity"), latest("environmental", "sbti_climate_target")

    def waci(weights: pd.Series) -> float | None:
        m = ghg.notna() & (weights > 0)
        return float((ghg[m] * weights[m]).sum() / weights[m].sum()) if weights[m].sum() else None

    def target_share(weights: pd.Series) -> float | None:
        m = sbti.notna() & (weights > 0)
        return float(weights[m & (sbti >= 2)].sum() / weights[m].sum()) if weights[m].sum() else None

    return {
        "waci_tco2e_per_musd": {"portfolio": waci(w), "benchmark": waci(b)},
        "sbti_target_share": {"portfolio": target_share(w), "benchmark": target_share(b)},
        "net_zero_validated_share": {
            "portfolio": float(w[sbti == 4].sum() / w[sbti.notna()].sum()) if w[sbti.notna()].sum() else None,
            "benchmark": float(b[sbti == 4].sum() / b[sbti.notna()].sum()) if b[sbti.notna()].sum() else None,
        },
    }


# ---------------------------------------------------------------- data + CLI
def load_universe() -> pd.DataFrame:
    return pd.read_csv(UNIVERSE_CSV, dtype=str, keep_default_na=False)


def load_market(universe: pd.DataFrame, month: str | None = None) -> tuple[pd.Series | None, dict]:
    """Market caps by CIK at `month` (default: the latest month-end with prices) + coverage info.
    (None, info) when the market data CSVs do not exist."""
    from portfolio.marketdata import MarketData

    md = MarketData.load()
    if md is None:
        return None, {"available": False}
    month = month or md.latest_month(list(universe["ticker"]))
    caps = md.caps(universe, month)
    have = caps["cap_usd"].notna()
    return caps["cap_usd"], {
        "available": True, "month": month, "companies": int(len(caps)), "with_cap": int(have.sum()),
        "coverage": float(have.mean()), "total_cap_usd": float(caps["cap_usd"].sum()),
        "missing": [{"cik": c, "detail": caps.at[c, "detail"]} for c in caps.index[~have]],
    }


def build_portfolio(profile_name: str = DEFAULT_PROFILE, fund_usd: float = 1e9) -> pd.DataFrame:
    """Scores the profile, allocates, writes scores/<profile>/portfolio.csv, prints a summary."""
    from common.score import build_scores, load_profile

    profile = load_profile(profile_name)
    scores = build_scores(profile_name)
    universe = load_universe()
    s = settings_for(profile, None, set(universe["sub_industry"]))
    caps, info = load_market(universe) if s["benchmark"] == "cap" else (None, {"available": False})
    portfolio = allocate(scores, profile, universe, caps)
    table = companies(scores, universe).set_index("ticker")
    out = portfolio.assign(
        usd=(portfolio["weight"] * fund_usd).round(0),
        name=portfolio["ticker"].map(table["name"]),
        sector=portfolio["ticker"].map(table["sector"]),
        sub_industry=portfolio["ticker"].map(table["sub_industry"]),
        total_score=portfolio["ticker"].map(table["total_score"]),
    )[["ticker", "name", "sector", "sub_industry", "total_score", "benchmark_weight", "weight", "active_weight", "usd", "status", "reason"]]
    path = SCORES_DIR / profile_name / "portfolio.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(path, index=False, lineterminator="\n")

    sm = summary(scores, portfolio, universe)
    bench_name = "cap-weighted" if s["benchmark"] == "cap" else "equal-weight"
    print(f"  portfolio '{profile_name}': {s}")
    if info.get("available"):
        print(f"  benchmark: market caps at {info['month']} month-end for {info['with_cap']} of {info['companies']} companies "
              f"({info['coverage']:.1%})")
    print(f"  {sm['holdings']} holdings of {sm['companies']} companies, {sm['excluded_policy']} excluded by sub-industry, "
          f"{sm['excluded_score']} by score, {sm['no_market_cap']} without market cap")
    print(f"  max weight {sm['max_weight']:.2%}, top 10 = {sm['top10_weight']:.1%} (benchmark {sm['benchmark_top10_weight']:.1%}), "
          f"active share {sm['active_share']:.1%}, unscored companies {sm['unscored_weight']:.1%}")
    for col, v in sm["scores"].items():
        f = "  n/a" if v["portfolio"] is None else f"{v['portfolio']:5.1f}"
        bm = "  n/a" if v["benchmark"] is None else f"{v['benchmark']:5.1f}"
        print(f"  {col:<22} fund {f}   {bench_name} benchmark {bm}")
    c = sm["climate"]
    if c["waci_tco2e_per_musd"]["portfolio"] is not None:
        print(f"  carbon intensity (WACI) fund {c['waci_tco2e_per_musd']['portfolio']:.1f} vs benchmark "
              f"{c['waci_tco2e_per_musd']['benchmark']:.1f} tCO2e/$M revenue; science-based target share fund "
              f"{c['sbti_target_share']['portfolio']:.1%} vs {c['sbti_target_share']['benchmark']:.1%}")
    print(f"  wrote {path.relative_to(ROOT).as_posix()} (fund {fund_usd:,.0f} USD)")
    return out
