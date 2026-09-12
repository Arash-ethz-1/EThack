# L2: facility -> ticker. THE CRITICAL PATH. OWNER: Arash.
# In:  facility_emissions (Jean) + EX-21 subsidiary registry (Arash)
# Out: facility_ticker
#
# Approach, in order of how much of the work each step does:
#   1. EX-21 exact match after normalising legal suffixes  (does most of the work)
#   2. embedding retrieval over the registry for the rest  (handles abbreviations, d/b/a)
#   3. a small trained reranker on data/manual/link_labels.csv
#   4. manual overrides for the top 200 facilities by tonnage
#
# Publish precision and recall on held-out labels. An unmeasured join is a guess,
# and this one silently drops tonnage when it fails - which is why it gets a number.

from __future__ import annotations

import pandas as pd

LEGAL_SUFFIXES = (
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "lp",
    "llp", "ltd", "limited", "plc", "holdings", "holding", "group", "sa", "nv",
    "ag", "gmbh", "trust", "partnership", "lllp", "pllc",
)


def normalise(name: str) -> str:
    # "PUGET HOLDINGS LLC (100%)" -> "puget"
    raise NotImplementedError


def resolve(facilities: pd.DataFrame, registry: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print("run python run.py link")
