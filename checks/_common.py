"""Shared helpers for checks/*.py - not a check itself, imported by them.

A "check" is one file with TITLE, KIND ("code" or "agent"), EXHIBIT and a run()
function returning {"status", "verdict", "numbers", "rows"}. See docs/DASHBOARD.md
section 4. `python run.py verify [check_id]` runs them and writes checks/results/.
"""

from __future__ import annotations

import pandas as pd

from common.config import CATEGORIES, catalog_path, indicator_path


def all_indicators() -> list[dict]:
    """Every catalog row across all 3 categories, any status, with its file path."""
    rows = []
    for category in CATEGORIES:
        catalog = pd.read_csv(catalog_path(category), dtype=str, keep_default_na=False)
        for _, row in catalog.iterrows():
            rows.append(
                {
                    "category": category,
                    "indicator_id": row["indicator_id"],
                    "higher_is_better": row["higher_is_better"],
                    "status": row["status"],
                    "path": indicator_path(category, row["indicator_id"]),
                }
            )
    return rows


def read_indicator(path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.exists() else None
