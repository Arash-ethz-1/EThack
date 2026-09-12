# Shared dashboard helpers. OWNER: Arash.
# Import from here in your page rather than re-reading parquet yourself.

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ethack.config import MOCK, PROCESSED  # noqa: E402


def data_dir() -> Path:
    # Prefer real output; fall back to mocks so the app ALWAYS runs.
    real = ROOT / PROCESSED
    if (real / "company_scores.parquet").exists():
        return real
    return ROOT / MOCK


def is_mock() -> bool:
    return data_dir().name == "mock"


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(data_dir() / f"{name}.parquet")


def mock_banner() -> None:
    if is_mock():
        st.warning(
            "Showing SYNTHETIC data. Every figure on this page is generated. "
            "Run `make all` to replace it with real output.",
            icon=":material/science:",
        )
