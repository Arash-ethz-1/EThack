# OWNER: Arash. See docs/tasks/arash.md
# Contract in / out: -> subsidiary registry, feeds link.py


# The ownership ground truth. For each S&P 500 CIK:
#   1. data.sec.gov/submissions/CIK{cik:010d}.json  -> latest 10-K accession
#   2. .../Archives/edgar/data/{cik}/{accession}/index.json -> find *exx21*.htm
#   3. strip tags, one subsidiary per line, label with the parent ticker
# Verified: Duke (CIK 1326160) yields 186 subsidiaries incl. "Cinergy Corp".
# SEC needs a User-Agent header (config.SEC_USER_AGENT) or it 403s.


from __future__ import annotations

import pandas as pd


def fetch(refresh: bool = False) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print(fetch().head())
