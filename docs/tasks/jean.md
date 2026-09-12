# Jean - environmental impact

**Area:** `environmental/`
**Goal phase 1:** >= 3 `ready` environmental indicators in `environmental/catalog.csv`.

## Getting started (no git knowledge needed)

1. Open the `EThack` folder in Claude Code.
2. Type `/start`. The agent pulls the latest work and tells you where things stand.
3. Tell it what you want in normal words, e.g. *"Let's build the GHG intensity indicator."*
4. Type `/save` whenever something works, and before you stop.

## Candidate indicators (verify coverage before building)

| id | idea | direction | watch out |
|---|---|---|---|
| `ghg_intensity` | EPA GHGRP metered Scope 1 tCO2e / $M revenue | lower better | GHGRP is per facility with a `parent_company` name -> map to ticker. Name matching is the hard part; SEC EX-21 subsidiary lists help. |
| `toxic_releases` | EPA TRI toxic releases (lbs) / $M revenue | lower better | TRI has a parent company field; same mapping problem |
| `env_violations` | EPA ECHO enforcement penalties / $M revenue | lower better | facility-level, same mapping |
| `climate_target` | validated science-based target (SBTi target dashboard) (1/0 or target ambition) | higher better | binary -> many ties |

Facility -> company mapping is shared work for the first three - build it once in
`environmental/scripts/_facility_to_ticker.py` (files starting with `_` are helpers,
`build` does not run them) and reuse it.

Endpoints tested in the old repo (see git history, commit `1c89ef2`, CLAUDE.md section 5):
- `https://data.epa.gov/efservice/pub_dim_facility/year/2023/JSON`
- `https://data.epa.gov/efservice/pub_facts_sector_ghg_emission/year/2023/JSON`
- `https://echodata.epa.gov/echo/cwa_rest_services.get_facilities`

## Needs from others

- Arash: `universe/sp500.csv`; `universe/financials.csv` (revenue per company) for the intensity denominators

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->

### 2026-09-12 - resource_supply_risk

- Done: built `resource_supply_risk`, status `ready`. 3521 rows, 503/503 companies,
  2018-2024. Measures how exposed a company's industry is to raw materials that are
  hard to get. Two halves, both from live sources, no hand-entered numbers:
  - **material supply risk** (`scripts/_resource_risk.py`): 50% production
    concentration (HHI of country shares of world production, USGS Mineral Commodity
    Summaries 2026) + 50% governance of the producing countries (World Bank WGI:
    political stability, rule of law, control of corruption), weighted by production
    share. 76 materials. This is the BGS Risk List idea rebuilt from sources that
    still publish.
  - **industry material intensity** (`scripts/material_bills.csv`,
    `scripts/subindustry_exposure.csv`): each of the 127 GICS sub-industries in the
    S&P 500 maps to one of 23 material baskets and an intensity 0-1.
- Sanity check passed: highest 2024 scores are Semiconductors 50.25, Aerospace &
  Defense 47.84, Automobile Manufacturers 46.29; lowest are insurers and asset
  managers at 1.84. Highest-risk materials computed are Gallium 76.2, Niobium 72.4,
  Cobalt 68.6, Graphite 60.2, Tungsten 60.1 - that ranking matches the USGS critical
  minerals list, which is the check I wanted.
- Problems, both real and worth knowing before anyone leans on this:
  1. **The 7-year series is almost flat.** Mean across the index moves 21.27 (2018)
     to 21.50 (2024). Production shares are fixed at the 2025 USGS snapshot, so the
     only thing that varies by year is governance, and governance barely moves.
     The cross-section is informative; the time series currently is not.
  2. **Every company in a sub-industry gets the same score.** 79 distinct values
     across 503 companies in 2024. It is a sub-industry index, not a company
     measurement. Next step below fixes this.
  3. 6 materials (crushed stone, construction sand and gravel, and the noble gases)
     have no country breakdown in USGS, so they are dropped rather than scored as
     perfectly concentrated. Neon matters for chip lithography and is a real gap.
- Next: `critical_material_exposure` - EDGAR full-text search over each company's own
  10-K for the materials it names, weighted by that material's supply risk. Verified
  the API works and is cheap (`"rare earth"` returns 96 10-K hits for 2023, each with
  the filer's CIK). That gives per-company, per-year evidence with a citable filing,
  which is what fixes problems 1 and 2.
- Needs from others: Arash - `universe/sp500.csv`. Until it exists I take the ticker
  list from a cached S&P 500 constituents file in `environmental/raw/`; the script
  switches over automatically once the real file lands.

