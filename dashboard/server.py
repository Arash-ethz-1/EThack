"""Dashboard backend: a small local web server around common/score.py. No extra dependencies.

    python run.py dashboard        -> http://127.0.0.1:8500

The browser (dashboard/static/) only displays numbers. Every score comes from
common/score.py through the JSON API below:

    GET  /api/meta?source=real|demo     indicators, sectors, profiles
    GET  /api/profile?name=balanced     a saved profile
    POST /api/score                     {source, profile} -> ranking, sectors, correlations
    POST /api/explain                   {source, profile, ticker} -> one company's breakdown
    POST /api/profiles                  {profile} -> saves profiles/<name>.toml

Workspace - everything `python run.py ...` does, from the browser:

    GET  /api/workspace?fetch=1         git status, all catalog rows, format check
    POST /api/run                       {command, ...} -> starts `python run.py <command>` as a job
    GET  /api/job?id=...                output of a running / finished job

Only the commands in `job_args` can run, with checked arguments. The server listens on
127.0.0.1 only and POSTs need the X-EThack header, so other websites cannot trigger them.
"""

from __future__ import annotations

import json
import math
import mimetypes
import os
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

import run as cli  # noqa: E402
from common.config import CATEGORIES, DEFAULT_PROFILE, ROOT, catalog_path, indicator_path, scripts_dir  # noqa: E402
from common.demo import demo_dataset  # noqa: E402
from common.score import (  # noqa: E402
    Dataset,
    explain,
    list_profiles,
    load_dataset,
    load_profile,
    profile_from_dict,
    save_profile,
    score_profile,
)
from common.validate import ID_PATTERN, validate_all  # noqa: E402
from portfolio.allocate import OUTPUT_COLUMNS, PLANNED_SETTINGS  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
_demo: Dataset | None = None


# ---------------------------------------------------------------- api (plain functions, tested)
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


def get_dataset(source: str) -> Dataset:
    global _demo
    if source == "demo":
        if _demo is None:
            _demo = demo_dataset()
        return _demo
    return load_dataset()  # re-read every time, so new indicators show up without a restart


def records(df: pd.DataFrame) -> list[dict]:
    return [clean(r) for r in df.to_dict(orient="records")]


def api_meta(source: str) -> dict:
    real = load_dataset()
    data = get_dataset("demo") if source == "demo" else real
    n = len(data.universe)
    indicators = []
    for _, ind in data.catalog.iterrows():
        iid = ind["indicator_id"]
        values = data.values[iid].dropna() if iid in data.values else pd.Series(dtype=float)
        years = data.years[iid].dropna() if iid in data.years else pd.Series(dtype=float)
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
    return clean(
        {
            "source": "demo" if data.demo else "real",
            "has_real": not real.catalog.empty,
            "companies": n,
            "categories": list(CATEGORIES),
            "sectors": sorted(s for s in data.universe["sector"].unique() if s),
            "indicators": indicators,
            "profiles": list_profiles(),
            "default_profile": DEFAULT_PROFILE,
            "portfolio": {"output_columns": OUTPUT_COLUMNS, "settings": PLANNED_SETTINGS},
        }
    )


def api_profile(name: str) -> dict:
    return clean(asdict(load_profile(name)) | {"id": name})


def api_score(payload: dict) -> dict:
    data = get_dataset(payload.get("source", "real"))
    profile = profile_from_dict(to_toml_dict(payload["profile"]), "dashboard")
    result = score_profile(data, profile)
    table = result.table

    by_sector = []
    with_sector = table[table["sector"] != ""]
    for sector, part in with_sector.groupby("sector"):
        row = {"sector": sector, "companies": len(part), "scored": int(part["total_score"].notna().sum()),
               "total": part["total_score"].median()}
        row.update({c: part[f"{c}_score"].median() for c in CATEGORIES})
        by_sector.append(row)
    by_sector.sort(key=lambda r: -1 if pd.isna(r["total"]) else -r["total"])

    ranks = result.ranks.dropna(axis=1, how="all")
    corr = ranks.corr(method="spearman") if ranks.shape[1] >= 2 else pd.DataFrame()

    scored = table["total_score"].dropna()
    return clean(
        {
            "rows": records(table),
            "scored": int(scored.size),
            "median": scored.median() if scored.size else None,
            "weights": result.weights.to_dict(),
            "category_weights": result.category_weights.to_dict(),
            "sectors": by_sector,
            "correlation": {"ids": list(corr.columns), "matrix": corr.round(2).values.tolist()},
            "warnings": profile.warnings(data.catalog),
        }
    )


def api_explain(payload: dict) -> dict:
    data = get_dataset(payload.get("source", "real"))
    profile = profile_from_dict(to_toml_dict(payload["profile"]), "dashboard")
    result = score_profile(data, profile)
    ticker = payload["ticker"]
    row = result.table.set_index("ticker").loc[ticker]
    return clean({"company": {"ticker": ticker, **row.to_dict()}, "indicators": records(explain(data, result, ticker))})


def api_save_profile(payload: dict) -> dict:
    profile = profile_from_dict(to_toml_dict(payload["profile"]), payload["profile"].get("name", "profile"))
    path = save_profile(profile)
    return {"id": path.stem, "path": path.relative_to(ROOT).as_posix(), "profiles": list_profiles()}


def to_toml_dict(p: dict) -> dict:
    """Profile as sent by the browser -> the dict shape of a profiles/*.toml file."""
    return {
        "name": p.get("name", "Custom"),
        "description": p.get("description", ""),
        "categories": p.get("category_weights", {}),
        "indicators": p.get("indicator_weights", {}),
        "min_weight_share": p.get("min_weight_share", 0.5),
        "sector_relative": p.get("sector_relative", False),
        "portfolio": p.get("portfolio", {}),
    }


# ---------------------------------------------------------------- workspace (the run.py commands)
def api_workspace(fetch: bool) -> dict:
    if fetch:
        cli.git("fetch", "-q", "origin", cli.BRANCH)
    changes = []
    for line in cli.git_lines("status", "--porcelain"):
        path = line[3:].strip().strip('"').split(" -> ")[-1]
        changes.append({"status": line[:2].strip() or "?", "path": path, "owner": cli.owner_of(path)})

    def count(rng: str) -> int:
        return int(cli.git("rev-list", "--count", rng).stdout.strip() or 0)

    catalog = []
    for category in CATEGORIES:
        df = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        for _, row in df.iterrows():
            file = indicator_path(category, row["indicator_id"])
            info = {"category": category, "rows": 0, "companies": 0, "year_max": None}
            if file.exists():
                try:
                    ind = pd.read_csv(file)
                    info.update(rows=len(ind), companies=int(ind["ticker"].nunique()), year_max=int(ind["year"].max()))
                except Exception:  # broken file - the format check below reports it
                    pass
            script = scripts_dir(category) / f"{row['indicator_id']}.py"
            catalog.append(row.to_dict() | info | {"has_file": file.exists(), "has_script": script.exists()})

    report = validate_all()
    return clean(
        {
            "git": {
                "branch": cli.current_branch(),
                "changes": changes,
                "ahead": count(f"origin/{cli.BRANCH}..HEAD"),
                "behind": count(f"HEAD..origin/{cli.BRANCH}"),
                "user": cli.git("config", "user.name").stdout.strip(),
                "last_commit": cli.git("log", "-1", "--format=%s|%an|%ar").stdout.strip(),
            },
            "catalog": catalog,
            "check": {
                "errors": [{"area": a, "message": m} for a, m in report.errors],
                "warnings": [{"area": a, "message": m} for a, m in report.warnings],
            },
            "profiles": list_profiles(),
            "job": current_job(),
        }
    )


def job_args(payload: dict) -> tuple[str, list[str]]:
    """Browser request -> (title, run.py arguments). Anything else is refused."""
    cmd = payload.get("command")
    category, iid = payload.get("category", ""), payload.get("indicator_id", "")
    if cmd == "start":
        return "Get the team's latest work", ["start"]
    if cmd == "status":
        return "Status", ["status"]
    if cmd == "check":
        return "Format check + tests", ["check"]
    if cmd == "save":
        message = " ".join(str(payload.get("message", "")).split())
        if not message or len(message) > 200:
            raise ValueError("describe what you changed (1-200 characters)")
        return f"Save: {message}", ["save", message]
    if cmd in ("build", "new-indicator"):
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        if (cmd == "new-indicator" or iid) and not ID_PATTERN.match(iid):
            raise ValueError("indicator id must be lowercase_snake_case, e.g. ceo_pay_ratio")
        if cmd == "build":
            return f"Build {category}/{iid or 'all'}", ["build", category, *([iid] if iid else [])]
        return f"New indicator {category}/{iid}", ["new-indicator", category, iid]
    if cmd == "score":
        profile = payload.get("profile", DEFAULT_PROFILE)
        if profile not in list_profiles():
            raise ValueError(f"unknown profile '{profile}'")
        return f"Export scores: {profile}", ["score", profile]
    raise ValueError(f"unknown command '{cmd}'")


class Job:
    """One `python run.py ...` subprocess; output is collected line by line."""

    def __init__(self, title: str, args: list[str]):
        self.id, self.title, self.args = uuid.uuid4().hex[:12], title, args
        self.lines: list[str] = []
        self.code: int | None = None
        self.started = time.time()
        env = os.environ | {"PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
        self.proc = subprocess.Popen(
            [sys.executable, "run.py", *args], cwd=ROOT, env=env, text=True, encoding="utf-8",
            errors="replace", stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.append(line.rstrip("\n"))
        self.code = self.proc.wait()

    def to_dict(self) -> dict:
        return {
            "id": self.id, "title": self.title, "command": "python run.py " + " ".join(self.args),
            "running": self.code is None, "code": self.code, "output": self.lines[-400:],
            "seconds": round(time.time() - self.started),
        }


JOBS: dict[str, Job] = {}
_job_lock = threading.Lock()


def current_job() -> dict | None:
    running = [j for j in JOBS.values() if j.code is None]
    return running[0].to_dict() if running else None


def api_run(payload: dict) -> dict:
    title, args = job_args(payload)
    with _job_lock:
        if current_job():
            raise ValueError("another command is still running - wait until it finishes")
        job = Job(title, args)
        JOBS[job.id] = job
    return job.to_dict()


def api_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise KeyError(f"no job {job_id}")
    return JOBS[job_id].to_dict()


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
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/meta":
            return self.handle_api(api_meta, query.get("source", "real"))
        if url.path == "/api/profile":
            return self.handle_api(api_profile, query.get("name", DEFAULT_PROFILE))
        if url.path == "/api/workspace":
            return self.handle_api(api_workspace, query.get("fetch") == "1")
        if url.path == "/api/job":
            return self.handle_api(api_job, query.get("id", ""))

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
        routes = {"/api/score": api_score, "/api/explain": api_explain, "/api/profiles": api_save_profile,
                  "/api/run": api_run}
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
