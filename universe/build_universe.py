"""Build universe/sp500.csv - the S&P 500 company list every indicator joins on.

Owner:  Arash
Source: datasets/s-and-p-500-companies (the Wikipedia constituents table as CSV),
        CIKs cross-checked against SEC company_tickers.json
Run:    python universe/build_universe.py

Output: universe/sp500.csv with columns ticker, name, sector, cik (docs/DATA_FORMAT.md)
        + sub_industry (GICS Sub-Industry, used by portfolio exclusions)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from common.config import ROOT, UNIVERSE_COLUMNS, UNIVERSE_CSV
from common.io import cached_download, cached_json

AREA = "universe"  # cached_download stores raw files in universe/raw/
CONSTITUENTS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv"
)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def normalise_ticker(s: pd.Series) -> pd.Series:
    """Uppercase, dot not dash: BRK-B -> BRK.B."""
    return s.str.strip().str.upper().str.replace("-", ".", regex=False)


def build(refresh: bool = False) -> pd.DataFrame:
    path = cached_download(CONSTITUENTS_URL, AREA, "sp500_constituents.csv", refresh=refresh)
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    df = df.rename(columns={"Symbol": "ticker", "Security": "name", "GICS Sector": "sector", "CIK": "cik",
                            "GICS Sub-Industry": "sub_industry"})
    df["ticker"] = normalise_ticker(df["ticker"])
    df["cik"] = df["cik"].str.strip().str.zfill(10)
    df = df[UNIVERSE_COLUMNS + ["sub_industry"]]

    # Cross-check: does SEC map the same ticker to the same CIK?
    sec = pd.DataFrame(cached_json(SEC_TICKERS_URL, AREA, "sec_company_tickers.json", refresh=refresh).values())
    sec["ticker"] = normalise_ticker(sec["ticker"])
    sec["cik"] = sec["cik_str"].astype(str).str.zfill(10)
    sec_cik = sec.drop_duplicates("ticker").set_index("ticker")["cik"]
    known = df["ticker"].isin(sec_cik.index)
    mismatch = df[known & (df["ticker"].map(sec_cik) != df["cik"])]

    problems = []
    if df["ticker"].duplicated().any():
        problems.append(f"duplicate tickers: {df.loc[df['ticker'].duplicated(), 'ticker'].tolist()}")
    if (df == "").any().any():
        problems.append(f"empty cells:\n{df[(df == '').any(axis=1)]}")
    if not df["cik"].str.fullmatch(r"\d{10}").all():
        problems.append("CIK not 10 digits")
    if problems:
        raise ValueError("universe not written:\n" + "\n".join(problems))

    print(f"{len(df)} companies, {df['sector'].nunique()} sectors")
    print(f"CIK check vs SEC: {int(known.sum())} tickers found at SEC, {len(mismatch)} with a different CIK")
    for _, r in mismatch.iterrows():
        print(f"  WARN {r['ticker']}: constituents CIK {r['cik']}, SEC CIK {sec_cik[r['ticker']]} (kept constituents)")
    for t in df.loc[~known, "ticker"]:
        print(f"  WARN {t}: ticker not in SEC company_tickers.json")
    return df.sort_values("ticker").reset_index(drop=True)


if __name__ == "__main__":
    out = build(refresh="--refresh" in sys.argv)
    out.to_csv(UNIVERSE_CSV, index=False, lineterminator="\n")
    print(f"wrote {UNIVERSE_CSV.relative_to(ROOT).as_posix()}")
