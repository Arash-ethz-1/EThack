# OWNER: Jean. See docs/tasks/jean.md
# Contract in / out: -> enforcement (define your own, it feeds an indicator)


from __future__ import annotations

import pandas as pd


def fetch(refresh: bool = False) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print(fetch().head())
