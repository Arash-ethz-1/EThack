# Frozen dataframe contracts between layers.
# OWNER: Arash. Changing a schema requires the downstream owner's OK, and the same
# commit must update scripts/make_mocks.py. See CONVENTIONS.md section 1.

from __future__ import annotations

import pandas as pd

# L1 -- Jean. One row per facility per year.
FACILITY_EMISSIONS = {
    "facility_id": "int64",
    "year": "int64",
    "facility_name": "string",
    "parent_company_raw": "string",   # verbatim from EPA, e.g. "CINERGY CORP (100%)"
    "ownership_pct": "float64",
    "naics": "string",
    "state": "string",
    "lat": "float64",
    "lon": "float64",
    "co2e_t": "float64",
}

# L1 -- Jean. One row per company per year, self-reported. Every value cited.
COMPANY_REPORTED = {
    "ticker": "string",
    "year": "int64",
    "reported_scope1_t": "float64",
    "base_year": "Int64",
    "target_year": "Int64",
    "target_pct": "float64",
    "assurance_provider": "string",   # None means nobody audited the number
    "verbatim_quote": "string",       # mandatory: no citation, no row
    "source_url": "string",
    "page": "Int64",
}

# L1 -- Jean. Satellite / non-rescindable observation.
SATELLITE_EMISSIONS = {
    "asset_id": "string",
    "year": "int64",
    "lat": "float64",
    "lon": "float64",
    "sector": "string",
    "co2e_t": "float64",
    "source": "string",
}

# L1 -- Arash. Company fundamentals from SEC XBRL.
COMPANY_FINANCIALS = {
    "ticker": "string",
    "cik": "int64",
    "year": "int64",
    "revenue_usd": "float64",
    "ebitda_usd": "float64",
    "capex_usd": "float64",
    "sector": "string",
}

# L2 -- Arash. THE file everything downstream depends on.
FACILITY_TICKER = {
    "facility_id": "int64",
    "ticker": "string",
    "confidence": "float64",          # 0-1 from the reranker
    "match_method": "string",         # ex21_exact | ex21_embed | manual | unmatched
}

# L4 -- Lauren. One row per company. This is what the dashboard renders.
COMPANY_SCORES = {
    "ticker": "string",
    "sector": "string",
    "score": "float64",
    "ci_low": "float64",
    "ci_high": "float64",
    "tier": "string",                 # A-E; companies with overlapping CIs share a tier
    "visibility": "float64",          # 0-1: how much of this company we can actually see
    "coverage_ratio": "float64",      # metered US Scope 1 / disclosed global Scope 1
    "n_indicators_used": "int64",
}

# L5 -- Florian.
PORTFOLIO = {
    "ticker": "string",
    "sleeve": "string",
    "weight": "float64",
    "rationale": "string",
}

CONTRACTS = {
    "facility_emissions": FACILITY_EMISSIONS,
    "company_reported": COMPANY_REPORTED,
    "satellite_emissions": SATELLITE_EMISSIONS,
    "company_financials": COMPANY_FINANCIALS,
    "facility_ticker": FACILITY_TICKER,
    "company_scores": COMPANY_SCORES,
    "portfolio": PORTFOLIO,
}


class ContractViolation(AssertionError):
    pass


def validate(df: pd.DataFrame, name: str, *, strict: bool = True) -> pd.DataFrame:
    # Raise if df does not satisfy the named contract. Extra columns are allowed
    # unless strict=False is passed. Fail loudly on schema, never silently.
    if name not in CONTRACTS:
        raise KeyError(f"unknown contract {name!r}; known: {sorted(CONTRACTS)}")
    schema = CONTRACTS[name]
    missing = [c for c in schema if c not in df.columns]
    if missing:
        raise ContractViolation(f"{name}: missing columns {missing}")
    if strict:
        for col, dtype in schema.items():
            actual = str(df[col].dtype)
            if actual != dtype and not (dtype == "string" and actual == "object"):
                raise ContractViolation(
                    f"{name}.{col}: expected {dtype}, got {actual}"
                )
    return df


def empty(name: str) -> pd.DataFrame:
    # An empty frame with the right columns and dtypes. Useful as a stub return.
    schema = CONTRACTS[name]
    return pd.DataFrame({c: pd.Series(dtype=d) for c, d in schema.items()})
