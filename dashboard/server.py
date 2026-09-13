"""Dashboard backend: a small local web server around common/score.py and
checks/results/*.json. No new dependency beyond the stdlib.

    python run.py dashboard        -> http://127.0.0.1:8500

The dashboard only displays. Scores come from common/score.py; check results come
from checks/results/*.json (written by `python run.py verify`). No scoring,
ranking or model call happens in the browser or on page load.

    GET  /api/meta       indicators, sectors, profiles (with category weights)
    GET  /api/checks     every check's latest result, or "not_run" if it hasn't been
    POST /api/score      {profile, category_weights?} -> ranking table + sector medians
    POST /api/explain     {profile, category_weights?, ticker} -> one company's ledger
    POST /api/portfolio   {profile, category_weights?, settings?} -> holdings + fund vs benchmark
    POST /api/audit       {ticker, news?} -> filing quotes, EPA record, recent news for one company
    POST /api/evidence    {check, profile, category_weights?} -> an evidence check run live on those weights
    POST /api/netzero     {} -> the bonus answer: index vs exclusion-only vs net-zero fund, carbon price stress
    POST /api/trace       {profile, category_weights?, ticker} -> every step from source value to fund weight

The server listens on 127.0.0.1 only and POSTs need the X-EThack header, so other
websites cannot trigger them.
"""

from __future__ import annotations

import importlib
import json
import math
import mimetypes
import sys
import threading
import webbrowser
from dataclasses import asdict, replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from common.config import CATEGORIES, DEFAULT_PROFILE, ROOT, check_result_path, indicator_path  # noqa: E402
from common.score import explain, list_profiles, load_profile, peers, score_profile  # noqa: E402
from common.score import load_dataset as _load_dataset  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
CODE_CHECK_IDS = ["caught_later", "weight_robustness", "traceability", "plausibility", "stability", "redundancy", "sector_pattern", "cross_source_tax"]
AGENT_CHECK_IDS = ["agent_quote_verify"]
CHECK_IDS = CODE_CHECK_IDS + AGENT_CHECK_IDS


# ---------------------------------------------------------------- api (plain functions, tested)
_CACHE: dict = {}
_LOCK = threading.Lock()


def _signature() -> tuple:
    files = sorted(ROOT.glob("*/indicators/*.csv")) + sorted(ROOT.glob("*/catalog.csv")) + [ROOT / "universe" / "sp500.csv"]
    return tuple((str(f), f.stat().st_mtime_ns) for f in files if f.exists())


def load_dataset():
    """common.score.load_dataset, re-read only when an indicator, catalog or the universe changed -
    the start page runs several steps in a row and each would otherwise parse every CSV again."""
    sig = _signature()
    with _LOCK:
        if _CACHE.get("sig") != sig:
            _CACHE.clear()
            _CACHE.update(sig=sig, data=_load_dataset())
        return _CACHE["data"]


def cached(key: str, fn):
    """Memoise a slow, data-derived result for as long as the dataset signature holds."""
    load_dataset()
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    value = fn()
    with _LOCK:
        _CACHE[key] = value
    return value

def clean(obj):
    """JSON-safe: NaN -> null, numpy -> python."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if hasattr(obj, "item"):  # numpy scalar
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if obj is pd.NA or obj is pd.NaT:
        return None
    return obj


def records(df: pd.DataFrame) -> list[dict]:
    return [clean(r) for r in df.to_dict(orient="records")]


def api_meta() -> dict:
    data = load_dataset()
    n = len(data.universe)
    indicators = []
    retrieved_dates = []
    for _, ind in data.catalog.iterrows():
        iid = ind["indicator_id"]
        values = data.values[iid].dropna() if iid in data.values else pd.Series(dtype=float)
        years = data.years[iid].dropna() if iid in data.years else pd.Series(dtype=float)
        path = indicator_path(ind["category"], iid)
        if path.exists():
            retrieved_dates.append(pd.read_csv(path)["retrieved"].max())
        indicators.append(
            {
                "id": iid,
                "category": ind["category"],
                "name": ind["name"] or iid,
                "description": ind["description"],
                "unit": ind["unit"],
                "higher_is_better": ind["higher_is_better"] == "true",
                "catalog_weight": float(ind["weight"]),
                "source": ind["source"],
                "owner": ind["owner"],
                "companies": len(values),
                "coverage": len(values) / n if n else 0,
                "year_min": int(years.min()) if len(years) else None,
                "year_max": int(years.max()) if len(years) else None,
            }
        )
    profiles = []
    for name in list_profiles():
        p = load_profile(name)
        profiles.append(
            {
                "id": name,
                "name": p.name,
                "description": p.description,
                "category_weights": p.category_weights,
                "min_weight_share": p.min_weight_share,
                "indicator_weights": p.indicator_weights,
            }
        )
    return clean(
        {
            "companies": n,
            "categories": list(CATEGORIES),
            "sectors": sorted(s for s in data.universe["sector"].unique() if s),
            "indicators": indicators,
            "profiles": profiles,
            "default_profile": DEFAULT_PROFILE,
            "retrieved": max(retrieved_dates) if retrieved_dates else None,
        }
    )


def _profile_from_payload(payload: dict):
    base = load_profile(payload.get("profile", DEFAULT_PROFILE))
    weights = payload.get("category_weights")
    if weights:
        base = replace(base, category_weights={c: float(weights.get(c, 0)) for c in CATEGORIES})
    indicators = payload.get("indicator_weights")  # {indicator_id: weight}; 0 switches one off
    if indicators:
        base = replace(base, indicator_weights={**base.indicator_weights, **{k: float(v) for k, v in indicators.items()}})
    return base


def api_score(payload: dict) -> dict:
    data = load_dataset()
    profile = _profile_from_payload(payload)
    result = score_profile(data, profile)
    table = result.table

    by_sector = []
    with_sector = table[table["sector"] != ""]
    for sector, part in with_sector.groupby("sector"):
        row = {
            "sector": sector,
            "companies": len(part),
            "scored": int(part["total_score"].notna().sum()),
            "total": part["total_score"].median(),
        }
        row.update({c: part[f"{c}_score"].median() for c in CATEGORIES})
        by_sector.append(row)
    by_sector.sort(key=lambda r: -1 if pd.isna(r["total"]) else -r["total"])

    # per-company, per-indicator points (rank * 100) for the ranking table's fingerprint -
    # already computed by common/score.py as result.ranks, just also exposed here so the
    # browser never has to rank anything itself.
    fingerprints = {}
    for ticker, row in result.ranks.iterrows():
        points = {iid: round(float(r) * 100) for iid, r in row.items() if pd.notna(r)}
        if points:
            fingerprints[ticker] = points

    scored = table["total_score"].dropna()
    return clean(
        {
            "rows": records(table),
            "fingerprints": fingerprints,
            "scored": int(scored.size),
            "median": scored.median() if scored.size else None,
            "category_weights": result.category_weights.to_dict(),
            "sectors": by_sector,
            "warnings": profile.warnings(data.catalog),
        }
    )


def _source_lookup(category: str, indicator_id: str, ticker: str, year) -> dict:
    """One row's source, source_url and note straight from its indicator CSV -
    explain() only carries the value/rank/points, not provenance."""
    path = indicator_path(category, indicator_id)
    if not path.exists() or pd.isna(year):
        return {"source": "", "source_url": "", "note": ""}
    df = pd.read_csv(path)
    match = df[(df["ticker"] == ticker) & (df["year"] == int(year))]
    if match.empty:
        return {"source": "", "source_url": "", "note": ""}
    r = match.iloc[0]
    return {"source": r.get("source", ""), "source_url": r.get("source_url", ""), "note": r.get("note", "")}


def api_explain(payload: dict) -> dict:
    data = load_dataset()
    profile = _profile_from_payload(payload)
    result = score_profile(data, profile)
    ticker = payload["ticker"]
    row = result.table.set_index("ticker").loc[ticker]
    indicators = explain(data, result, ticker)
    for i, r in indicators.iterrows():
        for k, v in _source_lookup(r["category"], r["indicator_id"], ticker, r["year"]).items():
            indicators.at[i, k] = v
    return clean({"company": {"ticker": ticker, **row.to_dict()}, "indicators": records(indicators)})


def api_portfolio(payload: dict) -> dict:
    """portfolio/allocate.py on the chosen profile: holdings, fund-vs-benchmark summary,
    climate numbers and (when price data exists) ex-ante risk. `settings` overrides the
    profile's [portfolio] block for this request only - nothing is saved."""
    from portfolio.allocate import SETTINGS, allocate, companies, load_market, settings_for, summary
    from portfolio.allocate import load_universe as load_portfolio_universe
    from portfolio.risk import risk_report

    data = load_dataset()
    profile = _profile_from_payload(payload)
    overrides = {k: v for k, v in (payload.get("settings") or {}).items() if v is not None}
    universe = load_portfolio_universe()
    s = settings_for(profile, overrides, set(universe["sub_industry"]))
    table = score_profile(data, profile).table
    caps, market = load_market(universe) if s["benchmark"] == "cap" else (None, {"available": False})
    portfolio = allocate(table, profile, universe, caps, overrides)
    sm = summary(table, portfolio, universe)
    info = companies(table, universe).set_index("ticker")
    holdings = portfolio.assign(
        name=portfolio["ticker"].map(info["name"]), sector=portfolio["ticker"].map(info["sector"]),
        sub_industry=portfolio["ticker"].map(info["sub_industry"]), total_score=portfolio["ticker"].map(info["total_score"]),
    )
    sectors = sm.pop("sector_weights").rename_axis("sector").reset_index()
    return clean({
        "settings": s,
        "setting_help": SETTINGS,
        "sub_industries": sorted(x for x in universe["sub_industry"].unique() if x),
        "summary": sm,
        "sectors": records(sectors),
        "holdings": records(holdings),
        "market": {k: v for k, v in market.items() if k != "missing"},
        "risk": risk_report(portfolio),
    })


def api_audit(payload: dict) -> dict:
    """checks/_audit.py: filing quotes, regulator record and recent news for one company."""
    from checks._audit import audit

    return clean(audit(str(payload["ticker"]), with_news=payload.get("news", True), only_news=bool(payload.get("only_news"))))


EVIDENCE = {"caught_later": "checks.caught_later", "weight_robustness": "checks.weight_robustness"}


def api_evidence(payload: dict) -> dict:
    """Runs an evidence check on the weights the user chose - the same code as `python run.py verify`,
    so the exhibit shows what THIS weighting would have done, not a stored result."""
    import time

    cid = payload.get("check")
    if cid not in EVIDENCE:
        raise KeyError(f"unknown evidence check {cid!r}")
    mod = importlib.import_module(EVIDENCE[cid])
    profile = _profile_from_payload(payload)
    key = "evidence:" + cid + ":" + json.dumps({"p": payload.get("profile"), "w": profile.category_weights, "i": profile.indicator_weights}, sort_keys=True)
    started = time.perf_counter()
    result = cached(key, lambda: {**mod.run(profile=profile, data=load_dataset()), "seconds": round(time.perf_counter() - started, 2)})
    return clean({"id": cid, "title": mod.TITLE, "exhibit": mod.EXHIBIT, "live": True, **result})


def api_netzero(payload: dict) -> dict:
    """portfolio/transition.py: the bonus question's answer (fixed net_zero profile)."""
    from portfolio.transition import net_zero_answer

    profile = payload.get("profile", "net_zero")
    return clean(cached("netzero:" + profile, lambda: net_zero_answer(profile)))


def api_trace(payload: dict) -> dict:
    """One company, every step of the calculation with the numbers that went in - for the Method tab.
    All numbers come from common/score.py and portfolio/allocate.py; the browser only lays them out."""
    from portfolio.allocate import allocate, companies
    from portfolio.allocate import load_universe as load_portfolio_universe

    data = load_dataset()
    profile = _profile_from_payload(payload)
    ticker = str(payload["ticker"])
    result = score_profile(data, profile)
    row = result.table.set_index("ticker").loc[ticker]
    indicators = explain(data, result, ticker)
    steps_ind = []
    for _, r in indicators.iterrows():
        src = _source_lookup(r["category"], r["indicator_id"], ticker, r["year"])
        steps_ind.append({**r.to_dict(), **src, "comparison": peers(data, profile, ticker, r["indicator_id"])})
    pillars = []
    for c in CATEGORIES:
        terms = [{"indicator_id": x["indicator_id"], "name": x["name"], "weight": x["weight"],
                  "points": None if pd.isna(x["rank"]) else x["rank"] * 100} for x in steps_ind if x["category"] == c]
        pillars.append({"category": c, "score": row[f"{c}_score"], "weight": float(result.category_weights.get(c, 0.0)),
                        "weight_share": row[f"{c}_weight_share"], "terms": terms})

    universe = load_portfolio_universe()
    overrides = {k: v for k, v in (payload.get("settings") or {}).items() if v is not None}
    steps: dict = {}
    table = result.table
    portfolio = allocate(table, profile, universe, None, {**overrides, "benchmark": "equal"}, steps=steps)
    info = companies(table, universe).set_index("ticker")
    holding = ticker
    if ticker not in steps["benchmark"].index:  # a non-voting share class: the company is held under another ticker
        holding = next(t for t in steps["benchmark"].index if ticker in str(info.at[t, "other_classes"]))
    sec = steps["sectors"][holding]
    in_sec = steps["sectors"] == sec
    p = portfolio.set_index("ticker").loc[holding]
    fund = {
        "holding": holding, "settings": steps["settings"], "sector": sec, "status": p["status"], "reason": p["reason"],
        "total_score": info.at[holding, "total_score"], "mean": steps["scored_mean"], "std": steps["scored_std"],
        "companies": int(len(steps["benchmark"])), "benchmark": steps["benchmark"][holding], "eligible": steps["eligible"][holding],
        "z": steps["z"][holding], "tilted": steps["tilted"][holding],
        "sector_eligible": float(steps["eligible"][in_sec].sum()), "sector_tilted": float(steps["tilted"][in_sec].sum()),
        "tilt_factor": math.exp(max(-20.0, min(20.0, steps["settings"]["tilt_strength"] * steps["z"][holding]))) if steps["settings"]["method"] == "tilt" else None,
        "sector_factor": float(steps["eligible"][in_sec].sum() / steps["tilted"][in_sec].sum()) if steps["settings"]["sector_neutral"] and steps["tilted"][in_sec].sum() else None,
        "held_companies": int((steps["eligible"] > 0).sum()),
        "sector_neutral": steps["sector_neutral"][holding], "capped": steps["capped"][holding], "weight": p["weight"],
        "fund_usd": 1e9,
    }
    return clean({
        "company": {"ticker": ticker, **row.to_dict()},
        "profile": {"sector_relative": profile.sector_relative, "min_year": profile.min_year, "min_weight_share": profile.min_weight_share},
        "indicators": steps_ind, "pillars": pillars,
        "total": {"score": row["total_score"], "weights": result.category_weights.to_dict()},
        "fund": fund,
    })


def api_checks() -> dict:
    out = []
    for cid in CHECK_IDS:
        mod = importlib.import_module(f"checks.{cid}")
        path = check_result_path(cid)
        if path.exists():
            result = json.loads(path.read_text(encoding="utf-8"))
        else:
            result = {"status": "not_run", "verdict": "Not run yet.", "numbers": {}, "rows": [], "ran_at": None}
        out.append({"id": cid, "title": mod.TITLE, "kind": mod.KIND, "exhibit": mod.EXHIBIT, **result})
    return clean({"checks": out})


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # keep the terminal quiet
        pass

    def send_json(self, body, status=HTTPStatus.OK):
        data = json.dumps(body, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def handle_api(self, fn, *args):
        try:
            self.send_json(fn(*args))
        except (KeyError, ValueError, FileNotFoundError) as e:
            self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)

    def trusted(self) -> bool:
        """Blocks other websites: DNS rebinding (Host header) and cross-site POSTs (custom header)."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
        return host in ("127.0.0.1", "localhost")

    def do_GET(self):
        if not self.trusted():
            return self.send_error(HTTPStatus.FORBIDDEN)
        url = urlparse(self.path)
        if url.path == "/api/meta":
            return self.handle_api(api_meta)
        if url.path == "/api/checks":
            return self.handle_api(api_checks)

        rel = "index.html" if url.path in ("", "/") else url.path.lstrip("/")
        file = (STATIC / rel).resolve()
        if STATIC.resolve() not in file.parents or not file.is_file():
            return self.send_error(HTTPStatus.NOT_FOUND)
        data = file.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if not self.trusted() or self.headers.get("X-EThack") != "1":
            return self.send_error(HTTPStatus.FORBIDDEN)
        routes = {"/api/score": api_score, "/api/explain": api_explain, "/api/portfolio": api_portfolio, "/api/audit": api_audit,
                  "/api/evidence": api_evidence, "/api/netzero": api_netzero, "/api/trace": api_trace}
        fn = routes.get(urlparse(self.path).path)
        if fn is None:
            return self.send_error(HTTPStatus.NOT_FOUND)
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        except json.JSONDecodeError:
            return self.send_json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
        self.handle_api(fn, payload)


def serve(port: int = 8500, open_browser: bool = True) -> None:
    for candidate in range(port, port + 20):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", candidate), Handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"no free port between {port} and {port + 19}")
    # the net-zero answer parses ~130 SEC files (~15 s) - compute it once in the background now
    threading.Thread(target=lambda: api_netzero({}), daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"dashboard running at {url}  (Ctrl+C to stop)")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    serve(open_browser="--no-browser" not in sys.argv)
