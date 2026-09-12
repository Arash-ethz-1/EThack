import tomllib

import pandas as pd
import pytest

from common.demo import demo_dataset
from common.score import (
    Dataset,
    Profile,
    explain,
    list_profiles,
    load_profile,
    profile_from_dict,
    profile_to_toml,
    rank_table,
    score_profile,
    weighted_score,
)


def tiny_dataset() -> Dataset:
    universe = pd.DataFrame(
        {"ticker": ["A", "B", "C", "D"], "name": "", "sector": ["Energy", "Energy", "Tech", "Tech"]}
    )
    catalog = pd.DataFrame(
        [
            ("eco1", "true", "1", "economic"),
            ("soc1", "true", "1", "social"),
            ("env1", "false", "1", "environmental"),
            ("env2", "true", "1", "environmental"),
        ],
        columns=["indicator_id", "higher_is_better", "weight", "category"],
    ).assign(name="", unit="", status="ready")
    values = pd.DataFrame(
        {
            "eco1": [1.0, 2.0, 3.0, 4.0],
            "soc1": [4.0, 3.0, 2.0, 1.0],
            "env1": [100.0, 90.0, 2.0, 1.0],  # lower is better, Energy is far worse
            "env2": [1.0, None, 3.0, 4.0],
        },
        index=pd.Index(["A", "B", "C", "D"], name="ticker"),
    )
    return Dataset(universe, catalog, values, values.notna() * 2024)


def test_weighted_score_skips_missing_and_applies_coverage_rule():
    parts = pd.DataFrame({"x": [1.0, None], "y": [0.5, 1.0]}, index=["A", "B"])
    out = weighted_score(parts, pd.Series({"x": 3.0, "y": 1.0}), min_weight_share=0.5)
    assert out.loc["A", "score"] == pytest.approx(87.5)
    assert pd.isna(out.loc["B", "score"])  # has only 1/4 of the weight
    assert out.loc["B", "weight_share"] == 0.25


def test_unselected_indicator_is_ignored():
    data = tiny_dataset()
    both = score_profile(data, Profile("p")).table.set_index("ticker")
    only_env1 = score_profile(data, Profile("p", indicator_weights={"env2": 0})).table.set_index("ticker")
    assert both.loc["A", "environmental_n_indicators"] == 2
    assert only_env1.loc["A", "environmental_n_indicators"] == 1
    assert only_env1.loc["D", "environmental_score"] == 100.0


def test_category_weights_drive_total():
    data = tiny_dataset()
    only_eco = Profile("p", category_weights={"economic": 1, "social": 0, "environmental": 0})
    table = score_profile(data, only_eco).table.set_index("ticker")
    assert (table["total_score"] == table["economic_score"]).all()
    assert table.loc["D", "position"] == 1


def test_category_without_chosen_indicators_drops_out_of_total():
    data = tiny_dataset()
    profile = Profile("p", indicator_weights={"soc1": 0})
    result = score_profile(data, profile)
    assert list(result.category_weights.index) == ["economic", "environmental"]
    assert result.table["total_score"].notna().all()


def test_sector_relative_ranks_within_sector():
    data = tiny_dataset()
    sectors = data.universe.set_index("ticker")["sector"]
    ranks = rank_table(data.values, data.catalog, sectors)
    assert ranks.loc["B", "env1"] == 1.0  # best energy company, although worse than all tech
    assert rank_table(data.values, data.catalog).loc["B", "env1"] == pytest.approx(1 / 3)


def test_explain_points_add_up_to_total():
    data = demo_dataset()
    profile = Profile("p", category_weights={"economic": 1, "social": 2, "environmental": 3},
                      indicator_weights={"ghg_intensity": 4, "rd_intensity": 0})
    result = score_profile(data, profile)
    for ticker in result.table.dropna(subset=["total_score"])["ticker"][:20]:
        total = result.table.set_index("ticker").loc[ticker, "total_score"]
        assert explain(data, result, ticker)["points"].sum() == pytest.approx(total, abs=0.06)


def test_profile_toml_round_trip_and_validation():
    p = Profile("Net Zero", "d", {"economic": 1, "social": 0.5, "environmental": 3}, {"x": 0, "y": 2},
                0.4, True, {"method": "tilt"})
    assert profile_from_dict(tomllib.loads(profile_to_toml(p)), "net_zero") == p
    with pytest.raises(ValueError):
        profile_from_dict({"categories": {"governance": 1}}, "bad")
    with pytest.raises(ValueError):
        profile_from_dict({"indicators": {"x": -1}}, "bad")


def test_shipped_profiles_load():
    assert "balanced" in list_profiles()
    for name in list_profiles():
        load_profile(name)
