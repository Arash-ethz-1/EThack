from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ethack.config import MOCK  # noqa: E402


def _ensure_mocks() -> None:
    if not (ROOT / MOCK / "company_scores.parquet").exists():
        subprocess.run([sys.executable, "scripts/make_mocks.py"],
                       cwd=ROOT, check=True, capture_output=True)


@pytest.fixture(scope="session")
def mock_dir() -> Path:
    _ensure_mocks()
    return ROOT / MOCK


@pytest.fixture(scope="session")
def mock_panel(mock_dir: Path) -> pd.DataFrame:
    # The joined company-level panel every indicator is written against.
    fac = pd.read_parquet(mock_dir / "facility_emissions.parquet")
    link = pd.read_parquet(mock_dir / "facility_ticker.parquet")
    fin = pd.read_parquet(mock_dir / "company_financials.parquet")
    rep = pd.read_parquet(mock_dir / "company_reported.parquet")
    sat = pd.read_parquet(mock_dir / "satellite_emissions.parquet")

    metered = (fac[fac.year == 2023]
               .merge(link, on="facility_id")
               .groupby("ticker")["co2e_t"].sum()
               .rename("metered_scope1_t"))

    sat_by_ticker = (
        sat.assign(facility_id=sat["asset_id"].str.removeprefix("ct_").astype("int64"))
        .merge(link, on="facility_id")
        .groupby("ticker")["co2e_t"].sum()
        .rename("satellite_scope1_t")
    )

    panel = (fin.set_index("ticker")
             .join(metered)
             .join(rep.set_index("ticker")[["reported_scope1_t"]])
             .join(sat_by_ticker))
    return panel
