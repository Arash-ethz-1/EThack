"""Helpers every indicator script uses: cached downloads and writing indicator files."""

from __future__ import annotations

import csv
import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from common.config import (
    INDICATOR_COLUMNS,
    OPTIONAL_INDICATOR_COLUMNS,
    ROOT,
    UNIVERSE_CSV,
    indicator_path,
    raw_dir,
)
from common.validate import check_indicator_text, load_universe_tickers

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # dotenv is optional
    pass


def today_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def http_headers() -> dict[str, str]:
    # SEC returns 403 without a contact email in the User-Agent.
    email = os.getenv("SEC_CONTACT_EMAIL", "ethack@example.com")
    return {"User-Agent": f"EThack research {email}"}


def cached_download(
    url: str,
    category: str,
    filename: str,
    *,
    params: dict | None = None,
    refresh: bool = False,
    pause_s: float = 0.2,
) -> Path:
    """Download once into <category>/raw/<filename>; later calls read the file.

    Every real download is logged in <category>/raw/_downloads.csv (provenance).
    """
    path = raw_dir(category) / filename
    if path.exists() and not refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, params=params, headers=http_headers(), timeout=60)
    resp.raise_for_status()
    path.write_bytes(resp.content)
    time.sleep(pause_s)

    log = raw_dir(category) / "_downloads.csv"
    new = not log.exists()
    with log.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        if new:
            w.writerow(["file", "url", "retrieved_utc", "bytes"])
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        w.writerow([filename, resp.url, stamp, len(resp.content)])
    return path


def cached_json(url: str, category: str, filename: str, **kwargs) -> Any:
    return json.loads(cached_download(url, category, filename, **kwargs).read_text(encoding="utf-8"))


def load_universe() -> pd.DataFrame:
    if not UNIVERSE_CSV.exists():
        raise FileNotFoundError("universe/sp500.csv does not exist yet - see universe/README.md")
    return pd.read_csv(UNIVERSE_CSV, dtype={"cik": str})


def write_indicator(category: str, indicator_id: str, df: pd.DataFrame) -> Path:
    """Validate and write <category>/indicators/<indicator_id>.csv. Refuses bad data."""
    df = df.copy()
    if "note" not in df.columns:
        df["note"] = ""
    missing = [c for c in INDICATOR_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{indicator_id}: missing columns {missing}")
    df = df[INDICATOR_COLUMNS + OPTIONAL_INDICATOR_COLUMNS]
    df = df.dropna(subset=["value"]).sort_values(["ticker", "year"]).reset_index(drop=True)
    df["year"] = df["year"].astype(int)

    text = df.to_csv(index=False, lineterminator="\n")
    universe = load_universe_tickers()
    report = check_indicator_text(text, f"{category}/indicators/{indicator_id}.csv", universe)
    if report.errors:
        raise ValueError("indicator not written:\n" + "\n".join(f"  - {m}" for _, m in report.errors))

    path = indicator_path(category, indicator_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(
        f"wrote {path.relative_to(ROOT).as_posix()}: {len(df)} rows, {df['ticker'].nunique()} tickers, "
        f"years {df['year'].min()}-{df['year'].max()}"
    )
    for _, msg in report.warnings:
        print(f"  WARN {msg}")
    return path
