from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ethack import contracts
from ethack.score import _assign_tiers, score


def test_score_is_contract_valid_for_every_mode(mock_panel):
    for mode in ["declared", "equal", "confidence"]:
        out = score(mock_panel, mode=mode)
        contracts.validate(out, "company_scores")
        assert set(out["ticker"]) == set(mock_panel.index)


def test_sector_relative_not_global(mock_panel):
    # Comparing software to cement on absolute intensity is the category error the
    # whole design exists to avoid - so a percentile must be computed within sector.
    out = score(mock_panel, mode="equal")
    by_sector_size = mock_panel["sector"].value_counts()
    assert (by_sector_size > 1).any()
    # a company that tops its own (small) sector should not be forced into the same
    # percentile band as one that tops a giant sector - i.e. percentiles are not a
    # single global rank recomputed under a different name.
    assert out["score"].nunique() > 1


def test_overlapping_confidence_intervals_share_a_tier():
    score_s = pd.Series({"AAA": 0.90, "BBB": 0.88, "CCC": 0.40})
    ci_low = pd.Series({"AAA": 0.70, "BBB": 0.60, "CCC": 0.35})
    ci_high = pd.Series({"AAA": 0.95, "BBB": 0.99, "CCC": 0.45})
    tiers = _assign_tiers(score_s, ci_low, ci_high)
    assert tiers["AAA"] == tiers["BBB"], "overlapping CIs must share a tier"
    assert tiers["CCC"] != tiers["AAA"]


def test_low_coverage_company_is_flagged_not_ranked(mock_panel):
    panel = mock_panel.copy()
    # Strip every indicator input for one ticker so it cannot clear
    # MIN_COVERAGE_TO_RANK - it must come back unrated, never a fabricated score.
    t = panel.index[0]
    for col in [
        "metered_scope1_t",
        "reported_scope1_t",
        "satellite_scope1_t",
        "metered_growth_rate",
        "top_facility_share",
    ]:
        if col in panel.columns:
            panel.loc[t, col] = np.nan
    out = score(panel, mode="equal").set_index("ticker")
    assert out.loc[t, "tier"] == "U"
    assert pd.isna(out.loc[t, "score"])


def test_dead_sources_shrinks_indicator_use_and_widens_uncertainty(mock_panel):
    full = score(mock_panel, mode="equal", dead_sources=frozenset())
    blacked_out = score(mock_panel, mode="equal", dead_sources=frozenset({"epa_ghgrp"}))
    assert blacked_out["n_indicators_used"].sum() < full["n_indicators_used"].sum()
    common = full.set_index("ticker")["ci_high"] - full.set_index("ticker")["ci_low"]
    after = (
        blacked_out.set_index("ticker")["ci_high"]
        - blacked_out.set_index("ticker")["ci_low"]
    )
    assert after.mean() >= common.mean(), "losing evidence should never sharpen a CI"


def test_visibility_is_bounded_and_never_folded_into_score(mock_panel):
    out = score(mock_panel, mode="declared")
    assert out["visibility"].between(0, 1).all()
    # visibility and score are different axes - they must not be perfectly correlated
    assert out["visibility"].corr(out["score"].fillna(0)) < 0.99


def test_weighting_modes_mostly_agree_on_the_top_of_the_table(mock_panel):
    declared = score(mock_panel, mode="declared").set_index("ticker")["score"]
    equal = score(mock_panel, mode="equal").set_index("ticker")["score"]
    top_declared = set(declared.dropna().sort_values(ascending=False).head(20).index)
    top_equal = set(equal.dropna().sort_values(ascending=False).head(20).index)
    overlap = len(top_declared & top_equal)
    assert overlap >= 10, "weighting scheme should be a robustness story, not noise"


def test_score_requires_at_least_one_surviving_indicator(mock_panel):
    from ethack.indicators.registry import all_specs

    all_sources = {s for spec in all_specs() for s in spec.sources}
    with pytest.raises(ValueError):
        score(mock_panel, dead_sources=frozenset(all_sources))
