# Data acquisition. OWNER: Jean (epa, echo, satellite, reports), Arash (sec, ex21).
#
# Every module here must:
#   1. cache to data/raw/<name>.parquet and never re-fetch what it already has
#   2. append a provenance row to data/PROVENANCE.md (source, url, utc, rows, durability)
#   3. return a frame that passes contracts.validate()

SOURCE_DURABILITY = {
    "epa_ghgrp": "at_risk",
    "epa_echo": "at_risk",
    "sec_xbrl": "statutory",
    "sec_ex21": "statutory",
    "company_reports": "voluntary",
    "satellite": "permanent",
    "market": "permanent",
}
