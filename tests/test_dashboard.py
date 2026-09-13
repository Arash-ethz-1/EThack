import json
import math

from dashboard import server


def test_clean_makes_json_safe():
    out = server.clean({"a": float("nan"), "b": [1.5, float("inf")], "c": "x"})
    assert out == {"a": None, "b": [1.5, None], "c": "x"}


def test_meta_lists_ready_indicators_and_profiles():
    meta = server.api_meta()
    json.dumps(meta, allow_nan=False)
    assert meta["companies"] > 0
    assert {"economic", "social", "environmental"} <= set(meta["categories"])
    assert any(p["id"] == "balanced" for p in meta["profiles"])
    balanced = next(p for p in meta["profiles"] if p["id"] == "balanced")
    assert set(balanced["category_weights"]) == {"economic", "social", "environmental"}


def test_score_api_is_valid_json_and_sorted():
    result = server.api_score({"profile": "balanced"})
    json.dumps(result, allow_nan=False)
    assert result["scored"] > 0
    scores = [r["total_score"] for r in result["rows"] if r["total_score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_score_api_category_weight_override_switches_a_category_off():
    on = server.api_score({"profile": "balanced"})
    off = server.api_score({"profile": "balanced", "category_weights": {"economic": 0, "social": 1, "environmental": 1}})
    assert "economic" not in off["category_weights"]
    assert "economic" in on["category_weights"]


def test_explain_api_points_match_total():
    top = server.api_score({"profile": "balanced"})["rows"][0]
    detail = server.api_explain({"profile": "balanced", "ticker": top["ticker"]})
    assert math.isclose(sum(d["points"] for d in detail["indicators"]), top["total_score"], abs_tol=0.06)


def test_checks_api_reports_not_run_when_no_result_file(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "check_result_path", lambda cid: tmp_path / f"{cid}.json")
    result = server.api_checks()
    ids = {c["id"] for c in result["checks"]}
    assert ids == set(server.CHECK_IDS)
    assert all(c["status"] == "not_run" for c in result["checks"])


def test_checks_api_reads_a_real_result_file(tmp_path, monkeypatch):
    fake = {"status": "passed", "verdict": "ok", "numbers": {}, "rows": [], "ran_at": "2026-01-01T00:00:00Z"}
    path = tmp_path / "traceability.json"
    path.write_text(json.dumps(fake), encoding="utf-8")
    monkeypatch.setattr(server, "check_result_path", lambda cid: path if cid == "traceability" else tmp_path / "x.json")
    result = server.api_checks()
    trace = next(c for c in result["checks"] if c["id"] == "traceability")
    assert trace["status"] == "passed" and trace["kind"] == "code" and trace["exhibit"] == "A"


def test_portfolio_api_weights_sum_to_one_and_override_is_not_saved():
    result = server.api_portfolio({"profile": "balanced", "settings": {"tilt_strength": 0}})
    json.dumps(result, allow_nan=False)
    assert math.isclose(sum(h["weight"] for h in result["holdings"]), 1.0, abs_tol=1e-9)
    assert result["settings"]["tilt_strength"] == 0
    assert server.api_portfolio({"profile": "balanced"})["settings"]["tilt_strength"] != 0
    s = result["summary"]["scores"]["total_score"]
    assert abs(s["portfolio"] - s["benchmark"]) < 1.0  # strength 0 = benchmark after exclusions only
