# OWNER: Arash. See docs/tasks/arash.md
# Contract in / out: -> company_financials


from __future__ import annotations

import pandas as pd


def fetch(refresh: bool = False) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print(fetch().head())
