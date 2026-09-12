from __future__ import annotations

import pandas as pd
import pytest

from ethack import contracts


def test_every_mock_satisfies_its_contract(mock_dir):
    for name in ["facility_emissions", "company_reported", "satellite_emissions",
                 "company_financials", "facility_ticker", "company_scores"]:
        df = pd.read_parquet(mock_dir / f"{name}.parquet")
        contracts.validate(df, name)


def test_validate_rejects_missing_column():
    df = contracts.empty("company_scores").drop(columns=["visibility"])
    with pytest.raises(contracts.ContractViolation, match="visibility"):
        contracts.validate(df, "company_scores")


def test_empty_frames_are_valid():
    for name in contracts.CONTRACTS:
        contracts.validate(contracts.empty(name), name)
