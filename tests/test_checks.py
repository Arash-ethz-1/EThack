"""Small fixture-data tests for checks/*.py - one indicator's worth of made-up rows,
not the real repo data. Monkeypatches checks._common.all_indicators() so each check
runs against a controlled fixture instead of hitting the real catalog files.
"""

from __future__ import annotations

import pandas as pd
import pytest

from checks import plausibility, redundancy, sector_pattern, stability, traceability


def write_csv(path, rows):
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def fixture(monkeypatch, module, indicators: dict, tmp_path):
    """indicators: indicator_id -> list of row dicts. Patches all_indicators() in
    the given check module to return these, each backed by a real tmp CSV."""
    entries = []
    for iid, rows in indicators.items():
        path = write_csv(tmp_path / f"{iid}.csv", rows)
        entries.append({"category": "economic", "indicator_id": iid, "higher_is_better": "true",
                         "status": "ready", "path": path})
    monkeypatch.setattr(module, "all_indicators", lambda: entries)


BASE_ROW = {"source": "test", "source_url": "https://example.com/doc", "retrieved": "2026-01-01", "note": ""}


def rows_for(ticker_years: list[tuple[str, int, float]], url=None):
    return [
        {**BASE_ROW, "ticker": t, "year": y, "value": v, **({"source_url": url} if url else {})}
        for t, y, v in ticker_years
    ]


def test_traceability_flags_shared_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = rows_for([(f"T{i}", 2024, 1.0) for i in range(10)], url="https://shared.example.com/search")
    fixture(monkeypatch, traceability, {"fake_ind": rows}, tmp_path)
    result = traceability.run()
    assert result["status"] == "flagged"
    assert result["rows"][0]["indicator_id"] == "fake_ind"
    assert "shared" in result["rows"][0]["detail"] or "endpoint" in result["rows"][0]["detail"]


def test_traceability_passes_with_per_company_urls(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = [{**BASE_ROW, "ticker": f"T{i}", "year": 2024, "value": 1.0, "source_url": f"https://sec.gov/{i}"}
            for i in range(10)]
    fixture(monkeypatch, traceability, {"fake_ind": rows}, tmp_path)
    result = traceability.run()
    assert result["status"] == "passed"
    assert result["rows"] == []


def test_plausibility_flags_future_year(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = rows_for([("T1", 2099, 1.0)])
    fixture(monkeypatch, plausibility, {"fake_ind": rows}, tmp_path)
    result = plausibility.run()
    assert result["status"] == "flagged"
    assert any("future" in r["detail"] for r in result["rows"])


def test_plausibility_no_flag_when_deltas_are_uniform(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # 25 companies, identical +1 change every year - a "typical range" with iqr == 0;
    # must not flag every single transition against a degenerate fence
    rows = []
    for i in range(25):
        rows += rows_for([(f"T{i}", 2020, 1.0), (f"T{i}", 2021, 2.0), (f"T{i}", 2022, 3.0)])
    fixture(monkeypatch, plausibility, {"fake_ind": rows}, tmp_path)
    result = plausibility.run()
    assert result["rows"] == []


def test_stability_needs_minimum_overlap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = rows_for([(f"T{i}", 2020, float(i)) for i in range(5)] + [(f"T{i}", 2021, float(i)) for i in range(5)])
    fixture(monkeypatch, stability, {"fake_ind": rows}, tmp_path)
    result = stability.run()
    assert result["status"] == "flagged"  # only 5 companies overlap, below MIN_OVERLAP=100


def test_stability_detects_persistent_ranking(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    rows = rows_for([(f"T{i}", 2020, float(i)) for i in range(120)] + [(f"T{i}", 2021, float(i)) for i in range(120)])
    fixture(monkeypatch, stability, {"fake_ind": rows}, tmp_path)
    result = stability.run()
    assert result["status"] == "passed"
    assert result["numbers"]["series"]["fake_ind"][0]["rho"] == 1.0


def test_redundancy_flags_duplicate_indicators(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = rows_for([(f"T{i}", 2024, float(i)) for i in range(60)])
    b = rows_for([(f"T{i}", 2024, float(i) * 2) for i in range(60)])  # perfectly correlated with a
    fixture(monkeypatch, redundancy, {"ind_a": a, "ind_b": b}, tmp_path)
    result = redundancy.run()
    assert result["status"] == "flagged"
    assert result["numbers"]["pairs"]["ind_a|ind_b"]["rho"] == 1.0


def test_redundancy_passes_uncorrelated_indicators(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    a = rows_for([(f"T{i}", 2024, float(i)) for i in range(60)])
    b = rows_for([(f"T{i}", 2024, float((i * 37) % 60)) for i in range(60)])  # scrambled order
    fixture(monkeypatch, redundancy, {"ind_a": a, "ind_b": b}, tmp_path)
    result = redundancy.run()
    assert abs(result["numbers"]["pairs"]["ind_a|ind_b"]["rho"]) < 0.8


def test_sector_pattern_picks_most_tie_heavy_indicator(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tied = rows_for([(f"T{i}", 2024, 1.0 if i % 2 == 0 else 2.0) for i in range(30)])  # only 2 distinct values
    varied = rows_for([(f"T{i}", 2024, float(i)) for i in range(30)])  # all distinct
    monkeypatch.setattr(
        sector_pattern, "all_indicators",
        lambda: [
            {"category": "economic", "indicator_id": "tied", "path": write_csv(tmp_path / "tied.csv", tied)},
            {"category": "economic", "indicator_id": "varied", "path": write_csv(tmp_path / "varied.csv", varied)},
        ],
    )
    universe = pd.DataFrame({"ticker": [f"T{i}" for i in range(30)], "sector": ["Tech"] * 30})
    universe_path = tmp_path / "sp500.csv"
    universe.to_csv(universe_path, index=False)
    monkeypatch.setattr(sector_pattern, "UNIVERSE_CSV", universe_path)
    result = sector_pattern.run()
    assert result["numbers"]["indicator_id"] == "tied"
