from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ethack.config import MOCK
from ethack.score import build_panel


def _ensure_mocks() -> None:
    if not (ROOT / MOCK / "company_scores.parquet").exists():
        subprocess.run(
            [sys.executable, "scripts/make_mocks.py"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )


@pytest.fixture(scope="session")
def mock_dir() -> Path:
    _ensure_mocks()
    return ROOT / MOCK


@pytest.fixture(scope="session")
def mock_panel(mock_dir: Path) -> pd.DataFrame:
    # The joined company-level panel every indicator is written against. This is
    # score.build_panel() itself (Lauren owns it) so the test fixture and the real
    # pipeline can never silently drift apart.
    return build_panel(str(mock_dir))
