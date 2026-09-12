import json
import math

import pytest

from dashboard import server


def test_clean_makes_json_safe():
    out = server.clean({"a": float("nan"), "b": [1.5, float("inf")], "c": "x"})
    assert out == {"a": None, "b": [1.5, None], "c": "x"}


def test_score_api_on_demo_data_is_valid_json():
    profile = server.api_profile("balanced")
    result = server.api_score({"source": "demo", "profile": profile})
    json.dumps(result, allow_nan=False)
    assert result["scored"] > 0
    scores = [r["total_score"] for r in result["rows"] if r["total_score"] is not None]
    assert scores == sorted(scores, reverse=True)


def test_explain_api_points_match_total():
    profile = server.api_profile("net_zero")
    top = server.api_score({"source": "demo", "profile": profile})["rows"][0]
    detail = server.api_explain({"source": "demo", "profile": profile, "ticker": top["ticker"]})
    assert math.isclose(sum(d["points"] for d in detail["indicators"]), top["total_score"], abs_tol=0.06)


@pytest.mark.parametrize(
    "payload, args",
    [
        ({"command": "start"}, ["start"]),
        ({"command": "save", "message": "  [infra]  new   dashboard "}, ["save", "[infra] new dashboard"]),
        ({"command": "build", "category": "social"}, ["build", "social"]),
        ({"command": "build", "category": "social", "indicator_id": "ceo_pay_ratio"}, ["build", "social", "ceo_pay_ratio"]),
        ({"command": "new-indicator", "category": "economic", "indicator_id": "tax_gap"}, ["new-indicator", "economic", "tax_gap"]),
        ({"command": "score", "profile": "balanced"}, ["score", "balanced"]),
    ],
)
def test_allowed_commands(payload, args):
    assert server.job_args(payload)[1] == args


@pytest.mark.parametrize(
    "payload",
    [
        {"command": "push"},
        {"command": "save", "message": ""},
        {"command": "build", "category": "../etc"},
        {"command": "build", "category": "social", "indicator_id": "x; rm -rf /"},
        {"command": "new-indicator", "category": "social"},
        {"command": "score", "profile": "../secrets"},
    ],
)
def test_refused_commands(payload):
    with pytest.raises(ValueError):
        server.job_args(payload)
