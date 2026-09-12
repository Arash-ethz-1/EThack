# OWNER: Jean. See docs/tasks/jean.md
# Contract in / out: -> company_reported  (THIS IS THE AGENT ONE)


# AGENT LAYER. One extraction agent per company. Strict schema, mandatory citation:
# every row carries verbatim_quote + source_url + page, or it does not get written.
# If |extracted - metered| implies >2x divergence, a second agent re-reads and rules.
# Hand-collect the 50 largest emitters yourself FIRST - that is the accuracy benchmark
# you quote when a judge asks how you know the LLM was right.


from __future__ import annotations

import pandas as pd


def fetch(refresh: bool = False) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print(fetch().head())
