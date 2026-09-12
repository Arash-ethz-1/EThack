# L4: indicators -> scores. OWNER: Lauren.
# In:  the joined company panel
# Out: company_scores
#
# Non-negotiables, because these are what we are judged on:
#   * sector-relative percentiles - comparing software to cement is a category error
#   * bootstrap CIs, and companies whose intervals overlap SHARE a tier.
#     We refuse to claim #47 differs from #63 when the data cannot tell.
#   * a `visibility` column: how much of this company we can actually see
#   * run equal weights too, and report how little the ranking moves. Robustness
#     to your own weighting scheme is the answer when a judge attacks the weights.

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pandas as pd

from . import contracts
from .config import (
    BOOTSTRAP_N,
    DURABILITY_WEIGHT,
    MIN_COVERAGE_TO_RANK,
    MOCK,
    TIER_EDGES,
)
from .indicators.registry import surviving

_TIER_LABELS = ["A", "B", "C", "D", "E"]
_UNRATED = "U"


def build_panel(data_dir: str = MOCK) -> pd.DataFrame:
    # The company-level frame every indicator is written against. Reads the L1/L2
    # contracts straight off disk (mock or real - same filenames, same schema) so
    # this is the one place that turns "five separate files" into "one row per
    # ticker". No network, no writes: pure function over what is already on disk.
    fac = pd.read_parquet(f"{data_dir}/facility_emissions.parquet")
    link = pd.read_parquet(f"{data_dir}/facility_ticker.parquet")
    fin = pd.read_parquet(f"{data_dir}/company_financials.parquet")
    rep = pd.read_parquet(f"{data_dir}/company_reported.parquet")
    sat = pd.read_parquet(f"{data_dir}/satellite_emissions.parquet")

    fac_link = fac.merge(link, on="facility_id")
    latest_year = fac.year.max()
    latest = fac_link[fac_link.year == latest_year]

    metered = latest.groupby("ticker")["co2e_t"].sum().rename("metered_scope1_t")

    # asset_id embeds the facility id ONLY in mocks, so this join works on real
    # Climate TRACE data too only once Jean lands the spatial join - see
    # sources/satellite.py. Silently skip if the column shape does not match.
    sat_by_ticker = None
    if sat["asset_id"].str.fullmatch(r"ct_\d+").all():
        sat_by_ticker = (
            sat.assign(
                facility_id=sat["asset_id"].str.removeprefix("ct_").astype("int64")
            )
            .merge(link, on="facility_id")
            .groupby("ticker")["co2e_t"]
            .sum()
            .rename("satellite_scope1_t")
        )

    # metered_growth_rate: log-linear slope of metered tonnes across all available
    # years. This is the delivered trajectory - emissions_trajectory and
    # target_credibility both key off it.
    yearly = fac_link.groupby(["ticker", "year"])["co2e_t"].sum().reset_index()

    def _slope(group: pd.DataFrame) -> float:
        if len(group) < 2 or (group["co2e_t"] <= 0).any():
            return np.nan
        x = group["year"].to_numpy(dtype="float64")
        y = np.log(group["co2e_t"].to_numpy(dtype="float64"))
        return float(np.polyfit(x, y, 1)[0])

    growth = (
        yearly.groupby("ticker")
        .apply(_slope, include_groups=False)
        .rename("metered_growth_rate")
    )

    # top_facility_share: single-asset concentration risk, latest year only.
    fac_totals = latest.groupby("ticker")["co2e_t"].sum()
    fac_max = latest.groupby("ticker")["co2e_t"].max()
    top_facility_share = (fac_max / fac_totals.where(fac_totals > 0)).rename(
        "top_facility_share"
    )

    # link_confidence: mean facility<->ticker match confidence. A data-quality
    # signal, not a sustainability one - it feeds `visibility`, never the score.
    link_confidence = (
        link.groupby("ticker")["confidence"].mean().rename("link_confidence")
    )

    panel = (
        fin.set_index("ticker")
        .join(metered)
        .join(
            rep.set_index("ticker")[
                [
                    "reported_scope1_t",
                    "base_year",
                    "target_year",
                    "target_pct",
                    "assurance_provider",
                ]
            ]
        )
        .join(growth)
        .join(top_facility_share)
        .join(link_confidence)
    )
    if sat_by_ticker is not None:
        panel = panel.join(sat_by_ticker)
    else:
        panel["satellite_scope1_t"] = np.nan
    return panel


def _sector_percentile(raw: pd.Series, sector: pd.Series, direction: int) -> pd.Series:
    # Rank within sector, not across the whole index - comparing software to cement
    # on absolute tonnes is a category error. NaN stays NaN (na_option="keep").
    df = pd.DataFrame({"raw": raw, "sector": sector})
    ascending = direction == 1
    return (
        df.groupby("sector")["raw"]
        .rank(pct=True, ascending=ascending, na_option="keep")
        .rename(raw.name)
    )


def _resolve_weights(
    indicators: list,
    panel: pd.DataFrame,
    percentiles: dict[str, pd.Series],
    mode: str,
    weights: dict[str, float] | None,
) -> dict[str, float]:
    ids = [i.spec.id for i in indicators]
    if weights is not None:
        ids = [
            i for i in ids if i in weights
        ]  # the caller's dict is an inclusion mask too

    if mode == "equal":
        return {i: 1.0 for i in ids}

    if mode == "confidence":
        out = {}
        for ind in indicators:
            if ind.spec.id not in ids:
                continue
            coverage = percentiles[ind.spec.id].notna().mean()
            out[ind.spec.id] = coverage * DURABILITY_WEIGHT[ind.spec.durability.value]
        return out

    if mode != "declared":
        raise ValueError(f"unknown weighting mode {mode!r}")
    if weights is not None:
        return {i: weights[i] for i in ids}
    return {
        ind.spec.id: ind.spec.default_weight for ind in indicators if ind.spec.id in ids
    }


def _bootstrap_ci(
    values: np.ndarray,
    weights: np.ndarray,
    rng: np.random.Generator,
    n: int = BOOTSTRAP_N,
) -> tuple[float, float]:
    # Resample WHICH indicators we trust, not the underlying data - this is
    # deliberately about sensitivity to the indicator subset, computed by
    # resampling, never by a model. n < 2 indicators means we cannot say anything
    # about consistency, so the honest interval is the whole [0, 1] range.
    if len(values) < 2:
        return 0.0, 1.0
    idx = rng.integers(0, len(values), size=(n, len(values)))
    resampled = (values[idx] * weights[idx]).sum(axis=1) / weights[idx].sum(axis=1)
    return float(np.percentile(resampled, 2.5)), float(np.percentile(resampled, 97.5))


def _assign_tiers(
    score_s: pd.Series, ci_low: pd.Series, ci_high: pd.Series
) -> pd.Series:
    # Balanced base tiers from the score's own rank. Overlap is NOT transitive: with
    # ~10 indicators, CI width routinely exceeds the score gap between any two
    # rank-neighbours, so chaining "shares a tier with its neighbour" all the way
    # down the table collapses all 120 companies into tier A - technically
    # defensible one pair at a time, but a degenerate, useless result overall.
    #
    # So we bridge only the four A/B, B/C, C/D, D/E cut points, one pair at a time,
    # each judged against the ORIGINAL percentile-cut tiers (never against an
    # already-promoted neighbour). That keeps a promotion contained to the single
    # boundary pair the data genuinely cannot separate, instead of propagating.
    rank_order = score_s.sort_values(ascending=False).index
    pct_rank = score_s.rank(pct=True, ascending=True)

    def _base(p: float) -> str:
        if p >= TIER_EDGES[0]:
            return "A"
        if p >= TIER_EDGES[1]:
            return "B"
        if p >= TIER_EDGES[2]:
            return "C"
        if p >= TIER_EDGES[3]:
            return "D"
        return "E"

    base = {t: _base(pct_rank[t]) for t in score_s.index}
    tiers = dict(base)
    rank_of = {label: i for i, label in enumerate(_TIER_LABELS)}
    for prev, cur in pairwise(rank_order):
        if base[prev] == base[cur]:
            continue  # not a boundary pair - nothing to bridge
        overlap = ci_low[cur] <= ci_high[prev] and ci_low[prev] <= ci_high[cur]
        if overlap and rank_of[base[cur]] > rank_of[base[prev]]:
            tiers[cur] = base[prev]
    return pd.Series(tiers, index=score_s.index)


def score(
    panel: pd.DataFrame,
    weights: dict[str, float] | None = None,
    dead_sources: frozenset[str] = frozenset(),
    mode: str = "declared",  # declared | equal | confidence
    seed: int = 0,
) -> pd.DataFrame:
    # `dead_sources` is what makes the blackout simulator work: drop the indicators
    # that depend on a switched-off source, renormalise the surviving weights, and
    # recompute. Confidence intervals widen on their own as coverage falls, which is
    # the honest behaviour and also the demo.
    indicators = surviving(dead_sources)
    if not indicators:
        raise ValueError("no indicators survive this blackout scenario")

    raw = {ind.spec.id: ind.compute(panel) for ind in indicators}
    percentiles = {
        ind.spec.id: _sector_percentile(
            raw[ind.spec.id], panel["sector"], ind.spec.direction
        )
        for ind in indicators
    }

    # An indicator abstains (drops out of THIS run entirely) if too few companies
    # have it, per its own declared min_coverage. That is the spec, not a guess.
    usable = [
        ind
        for ind in indicators
        if percentiles[ind.spec.id].notna().mean() >= ind.spec.min_coverage
    ]
    if not usable:
        raise ValueError(
            "every indicator abstained - coverage too thin to score anything"
        )

    resolved_weights = _resolve_weights(usable, panel, percentiles, mode, weights)
    usable = [i for i in usable if i.spec.id in resolved_weights]

    pct_matrix = pd.DataFrame({i.spec.id: percentiles[i.spec.id] for i in usable})
    weight_vec = pd.Series({i.spec.id: resolved_weights[i.spec.id] for i in usable})

    n_used = pct_matrix.notna().sum(axis=1)
    n_total = len(usable)
    weighted_sum = pct_matrix.mul(weight_vec, axis=1).sum(axis=1, skipna=True)
    weight_totals = pct_matrix.notna().mul(weight_vec, axis=1).sum(axis=1)
    raw_score = (weighted_sum / weight_totals.where(weight_totals > 0)).rename("score")

    rng = np.random.default_rng(seed)
    ci_low = pd.Series(index=panel.index, dtype="float64")
    ci_high = pd.Series(index=panel.index, dtype="float64")
    for ticker in panel.index:
        row = pct_matrix.loc[ticker]
        present = row.notna()
        vals = row[present].to_numpy(dtype="float64")
        wts = weight_vec[present.index[present]].to_numpy(dtype="float64")
        lo, hi = _bootstrap_ci(vals, wts, rng)
        ci_low[ticker], ci_high[ticker] = lo, hi

    coverage_frac = n_used / n_total
    rankable = coverage_frac >= MIN_COVERAGE_TO_RANK

    final_score = raw_score.where(rankable)
    tiers = pd.Series(_UNRATED, index=panel.index, dtype="object")
    if rankable.any():
        tiers.loc[rankable] = _assign_tiers(
            final_score[rankable], ci_low[rankable], ci_high[rankable]
        )
    ci_low = ci_low.where(rankable, 0.0)
    ci_high = ci_high.where(rankable, 1.0)

    coverage_ratio = (
        panel["metered_scope1_t"]
        / panel["reported_scope1_t"].where(panel["reported_scope1_t"] > 0)
    ).replace([np.inf, -np.inf], np.nan)

    has_report = panel["reported_scope1_t"].notna().astype("float64")
    link_conf = panel.get("link_confidence", pd.Series(0.0, index=panel.index)).fillna(
        0.0
    )
    visibility = (
        0.5 * coverage_frac.clip(0, 1) + 0.3 * link_conf.clip(0, 1) + 0.2 * has_report
    ).clip(0, 1)

    out = pd.DataFrame(
        {
            "ticker": panel.index.astype("string"),
            "sector": panel["sector"].astype("string"),
            "score": final_score.astype("float64"),
            "ci_low": ci_low.astype("float64"),
            "ci_high": ci_high.astype("float64"),
            "tier": tiers.astype("string"),
            "visibility": visibility.astype("float64"),
            "coverage_ratio": coverage_ratio.astype("float64"),
            "n_indicators_used": n_used.astype("int64"),
        }
    ).reset_index(drop=True)
    return contracts.validate(out, "company_scores", strict=False)


def sensitivity_table(
    panel: pd.DataFrame, dead_sources: frozenset[str] = frozenset(), top_n: int = 20
) -> pd.DataFrame:
    # How much does the top-N actually move across the three weighting modes?
    # This table IS the answer when a judge attacks the weights.
    modes = ["declared", "equal", "confidence"]
    scores = {
        m: score(panel, dead_sources=dead_sources, mode=m).set_index("ticker")["score"]
        for m in modes
    }
    top_sets = {
        m: set(s.dropna().sort_values(ascending=False).head(top_n).index)
        for m, s in scores.items()
    }

    in_every_mode = set.intersection(*top_sets.values())
    rows = []
    for m in modes:
        overlap_with_declared = len(top_sets[m] & top_sets["declared"])
        rows.append(
            {
                "mode": m,
                f"top_{top_n}": sorted(top_sets[m]),
                f"shared_with_declared_top_{top_n}": overlap_with_declared,
                f"in_all_three_modes_top_{top_n}": len(in_every_mode),
            }
        )
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from .config import PROCESSED

    panel = build_panel()
    result = score(panel)
    Path(PROCESSED).mkdir(parents=True, exist_ok=True)
    result.to_parquet(f"{PROCESSED}/company_scores.parquet", index=False)

    print(
        f"scored {len(result)} companies, {result['tier'].eq('U').sum()} unrated "
        f"(coverage below {MIN_COVERAGE_TO_RANK:.0%})"
    )
    print(result["tier"].value_counts())
    print()
    print("sensitivity across weighting modes (top-20 overlap with 'declared'):")
    print(sensitivity_table(panel)[["mode", "shared_with_declared_top_20"]])
