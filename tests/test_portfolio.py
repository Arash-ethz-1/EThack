import pandas as pd
import pytest

from common.score import Profile
from portfolio.allocate import (
    allocate,
    apply_cap,
    benchmark_weights,
    exclude_worst,
    score_z,
    sector_neutralise,
    settings_for,
    summary,
    tilt,
)


def table(rows):
    return pd.DataFrame(rows, columns=["ticker", "sector", "total_score"])


def profile(**portfolio):
    return Profile(name="t", portfolio=portfolio)


def test_benchmark_is_equal_weight_without_market_caps():
    w = benchmark_weights(table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Energy", 60.0)]))
    assert w.to_dict() == pytest.approx({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3})


def test_benchmark_uses_market_caps_and_never_fills_missing():
    scores = table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Tech", 40.0)])
    w = benchmark_weights(scores, pd.Series({"A": 300.0, "B": 100.0}))  # C has no cap -> not in benchmark
    assert w.to_dict() == pytest.approx({"A": 0.75, "B": 0.25, "C": 0.0})


def test_z_is_neutral_for_unscored_and_zero_for_identical_scores():
    z = score_z(table([("A", "Tech", 80.0), ("B", "Tech", 40.0), ("C", "Energy", float("nan"))]))
    assert z["C"] == 0.0 and z["A"] > 0 > z["B"]
    assert score_z(table([("A", "Tech", 50.0), ("B", "Tech", 50.0)])).to_dict() == {"A": 0.0, "B": 0.0}


def test_tilt_strength_zero_is_benchmark_and_weights_stay_positive():
    bench = pd.Series({"A": 0.5, "B": 0.3, "C": 0.2})
    z = pd.Series({"A": 2.0, "B": 0.0, "C": -2.0})
    assert tilt(bench, z, 0.0).to_dict() == pytest.approx(bench.to_dict())
    out = tilt(bench, z, 50.0)  # extreme: clipped, no inf/nan
    assert out.notna().all() and (out > 0).all() and out.sum() == pytest.approx(1.0)
    assert out["A"] > bench["A"]


def test_sector_neutral_keeps_sector_totals_and_order_inside_sector():
    weights = pd.Series({"A": 0.60, "B": 0.20, "C": 0.15, "D": 0.05})
    bench = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    sectors = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy", "D": "Energy"})
    out = sector_neutralise(weights, bench, sectors)
    assert out[["A", "B"]].sum() == pytest.approx(0.5)
    assert out[["C", "D"]].sum() == pytest.approx(0.5)
    assert out["A"] > out["B"] and out["C"] > out["D"]


def test_cap_is_repeated_until_nobody_is_over_it():
    out = apply_cap(pd.Series({"A": 0.60, "B": 0.35, "C": 0.05}), 0.4)
    assert out.max() <= 0.4 + 1e-9 and out.sum() == pytest.approx(1.0)
    with pytest.raises(ValueError):
        apply_cap(pd.Series({"A": 0.5, "B": 0.5}), 0.1)  # 2 names cannot fit under 10%


def test_exclude_drops_worst_scored_but_never_unscored():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 10.0), ("C", "Energy", float("nan"))])
    out = exclude_worst(pd.Series({"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}), scores, 0.5)
    assert out["B"] == 0.0 and out["C"] > 0 and out.sum() == pytest.approx(1.0)


def test_allocate_fixed_columns_sum_to_one_and_leader_gains():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 10.0), ("C", "Energy", 50.0), ("D", "Energy", float("nan"))])
    out = allocate(scores, profile(max_weight=1.0))
    assert list(out.columns) == ["ticker", "weight", "benchmark_weight", "active_weight", "status", "reason"]
    assert out["weight"].sum() == pytest.approx(1.0)
    w = out.set_index("ticker")["weight"]
    assert w["A"] > w["B"]
    assert w[["A", "B"]].sum() == pytest.approx(0.5)  # sector-neutral by default
    assert "no score" in out.set_index("ticker").at["D", "reason"]


def test_profile_settings_override_defaults_and_are_validated():
    scores = table([("A", "Tech", 90.0), ("B", "Other", 10.0)])
    w = allocate(scores, profile(tilt_strength=0, sector_neutral=False, max_weight=1.0)).set_index("ticker")["weight"]
    assert w.to_dict() == pytest.approx({"A": 0.5, "B": 0.5})
    with pytest.raises(ValueError):
        settings_for(profile(method="pick"))
    with pytest.raises(ValueError):
        settings_for(profile(tilt_strenght=1))  # typo is an error, not silently ignored


def test_summary_shows_portfolio_beats_benchmark_score():
    scores = table([("A", "Tech", 90.0), ("B", "Tech", 10.0), ("C", "Energy", 60.0), ("D", "Energy", 40.0)])
    out = allocate(scores, profile(max_weight=1.0))
    s = summary(scores, out)
    assert s["holdings"] == 4
    assert s["scores"]["total_score"]["portfolio"] > s["scores"]["total_score"]["benchmark"]
    assert 0 < s["active_share"] < 1


def universe_for(rows):
    return pd.DataFrame(rows, columns=["ticker", "name", "sector", "cik", "sub_industry"])


def test_share_classes_are_one_holding_with_the_voting_class():
    scores = table([("GOOG", "Tech", 80.0), ("GOOGL", "Tech", 80.0), ("B", "Tech", 20.0)])
    uni = universe_for([("GOOG", "Alphabet C", "Tech", "1", "Media"), ("GOOGL", "Alphabet A", "Tech", "1", "Media"),
                        ("B", "B", "Tech", "2", "Software")])
    out = allocate(scores, profile(max_weight=1.0), uni).set_index("ticker")
    assert list(out.index.sort_values()) == ["B", "GOOGL"]
    assert out["benchmark_weight"].to_dict() == pytest.approx({"GOOGL": 0.5, "B": 0.5})  # counted once, not 2/3
    assert "also GOOG" in out.at["GOOGL", "reason"]


def test_excluding_a_whole_sector_does_not_readmit_it_through_sector_neutrality():
    scores = table([("X1", "Energy", 99.0), ("X2", "Energy", 98.0), ("T1", "Tech", 10.0), ("T2", "Tech", 20.0)])
    uni = universe_for([("X1", "", "Energy", "1", "Integrated Oil & Gas"), ("X2", "", "Energy", "2", "Integrated Oil & Gas"),
                        ("T1", "", "Tech", "3", "Software"), ("T2", "", "Tech", "4", "Software")])
    out = allocate(scores, profile(max_weight=1.0, exclude_sub_industries=["Integrated Oil & Gas"]), uni).set_index("ticker")
    assert out.loc[["X1", "X2"], "weight"].sum() == 0
    assert out["weight"].sum() == pytest.approx(1.0)
    assert (out.loc[["X1", "X2"], "status"] == "excluded_policy").all()
    with pytest.raises(ValueError):  # a typo in the exclusion list is an error
        allocate(scores, profile(exclude_sub_industries=["Integrated Oil and Gas"]), uni)


def test_cap_keeps_sector_totals_when_the_sector_can_hold_them():
    w = pd.Series({"A": 0.40, "B": 0.10, "C": 0.30, "D": 0.20})
    sectors = pd.Series({"A": "S1", "B": "S1", "C": "S2", "D": "S2"})
    out = apply_cap(w, 0.3, sectors)
    assert out.max() <= 0.3 + 1e-9
    assert out.sum() == pytest.approx(1.0)
    assert out[["A", "B"]].sum() == pytest.approx(0.5)
    assert out[["C", "D"]].sum() == pytest.approx(0.5)


def test_cap_weighted_benchmark_follows_market_caps_by_cik():
    scores = table([("A", "Tech", 50.0), ("B", "Tech", 50.0), ("C", "Other", 50.0)])
    uni = universe_for([("A", "", "Tech", "1", "S"), ("B", "", "Tech", "2", "S"), ("C", "", "Other", "3", "T")])
    caps = pd.Series({"1": 300.0, "2": 100.0, "3": float("nan")})
    out = allocate(scores, profile(benchmark="cap", max_weight=1.0), uni, caps).set_index("ticker")
    assert out["benchmark_weight"].to_dict() == pytest.approx({"A": 0.75, "B": 0.25, "C": 0.0})
    assert out.at["C", "status"] == "no_market_cap" and out.at["C", "weight"] == 0
