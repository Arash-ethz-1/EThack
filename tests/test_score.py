import pandas as pd
import pytest

from common.score import indicator_ranks, latest_values, score_category


def indicator(rows):
    return pd.DataFrame(rows, columns=["ticker", "year", "value"])


def catalog(rows):
    return pd.DataFrame(rows, columns=["indicator_id", "higher_is_better", "weight", "status"])


def test_latest_values_takes_most_recent_year():
    df = indicator([("A", 2022, 1.0), ("A", 2024, 3.0), ("A", 2023, 2.0), ("B", 2021, 5.0)])
    assert latest_values(df).to_dict() == {"A": 3.0, "B": 5.0}


def test_ranks_span_zero_to_one_and_flip_when_lower_is_better():
    values = pd.Series({"A": 10.0, "B": 20.0, "C": 30.0})
    assert indicator_ranks(values, True).to_dict() == {"A": 0.0, "B": 0.5, "C": 1.0}
    assert indicator_ranks(values, False).to_dict() == {"A": 1.0, "B": 0.5, "C": 0.0}


def test_ties_share_rank():
    ranks = indicator_ranks(pd.Series({"A": 1.0, "B": 1.0, "C": 2.0}), True)
    assert ranks["A"] == ranks["B"] == 0.25


def test_category_score_is_weighted_mean_times_100():
    cat = catalog([("x", "true", "1", "ready"), ("y", "false", "3", "ready"), ("z", "true", "1", "idea")])
    inds = {
        "x": indicator([("A", 2024, 1.0), ("B", 2024, 2.0)]),  # A=0, B=1
        "y": indicator([("A", 2024, 1.0), ("B", 2024, 2.0)]),  # lower better: A=1, B=0
    }
    scores, long = score_category(cat, inds)
    assert scores.loc["A", "score"] == pytest.approx(75.0)
    assert scores.loc["B", "score"] == pytest.approx(25.0)
    assert set(long["indicator_id"]) == {"x", "y"}  # 'idea' indicators are ignored


def test_company_with_too_little_weight_gets_no_score():
    cat = catalog([("x", "true", "1", "ready"), ("y", "true", "3", "ready")])
    inds = {
        "x": indicator([("A", 2024, 1.0), ("B", 2024, 2.0)]),
        "y": indicator([("B", 2024, 2.0), ("C", 2024, 1.0)]),
    }
    scores, _ = score_category(cat, inds)
    assert pd.isna(scores.loc["A", "score"])  # only 1/4 of the weight available
    assert scores.loc["B", "weight_share"] == 1.0


def test_universe_filter_drops_outside_tickers():
    cat = catalog([("x", "true", "1", "ready")])
    inds = {"x": indicator([("A", 2024, 1.0), ("B", 2024, 2.0), ("ZZZ", 2024, 99.0)])}
    scores, _ = score_category(cat, inds, universe={"A", "B"})
    assert set(scores.index) == {"A", "B"}
    assert scores.loc["B", "score"] == 100.0
