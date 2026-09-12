# OWNER: Jean. See docs/tasks/jean.md
# Contract in / out: -> facility_emissions


BASE = "https://data.epa.gov/efservice"

# Verified working:
#   {BASE}/pub_dim_facility/year/2023/rows/0:9999/JSON
#   {BASE}/pub_facts_sector_ghg_emission/year/2023/rows/0:9999/JSON
# Pull EVERY year from 2010 - the archive is the thesis, not just the latest snapshot.
# Envirofacts pages at 10k rows; loop the rows/N:M window until you get a short page.


from __future__ import annotations

import pandas as pd


def fetch(refresh: bool = False) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print(fetch().head())
