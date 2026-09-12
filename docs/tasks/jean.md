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

### 2026-09-12 - resource_supply_risk: extended to 2025

- Done: `resource_supply_risk` now covers 2019-2025 (was 2018-2024), 3521 rows,
  503/503 companies. USGS Mineral Commodity Summaries 2026 already has 2025 world
  production; World Bank governance data only goes to 2024. Rather than drop 2025,
  `_resource_risk.governance_risk()` carries each producing country's most recent
  available WGI estimate forward one year (governance moves slowly year to year, so
  this is a standard nowcast, not an invented number) and flags every row it applies
  to. Every 2025 row's `note` says so explicitly: "governance uses the most recent
  available World Bank estimate (2024)" - so nobody downstream mistakes a
  carried-forward number for a fresh 2024->2025 measurement.
- `python run.py check`: 13 tests pass, format check OK.
- Next: same as above - `critical_material_exposure` from EDGAR full-text search,
  fetch running in background (166/168 term-years cached as of this entry).

### 2026-09-12 - critical_material_disclosure: first build

- Done: built `critical_material_disclosure`, status `in_progress`. 1450 rows,
  296/503 companies ever, 2019-2025. Reads each company's own 10-K via SEC EDGAR
  full-text search for 23 critical-material terms, sums the USGS+WGI supply risk
  (`resource_supply_risk`'s scale) of whatever materials it names. Every row cites
  the actual filing (`environmental/scripts/_edgar_materials.py:filing_url`).
  Top of 2025: NEM 833.5 (17 materials), ALB 798.3 (16), FCX 504.8 (10) - miners and
  battery-material refiners disclosing the most, which is the right direction.
- Coverage in the latest single year is 226/503 = 45%, below the 70% bar for
  `ready` (AGENTS.md section 4), so it stays `in_progress` honestly rather than
  scored. This is company-level evidence to sit alongside `resource_supply_risk`
  (the industry-average version), not a replacement for it.
- `python run.py check`: 13 tests pass, format check OK.
- Needs from others: none blocking. Would like a second pair of eyes on
  `environmental/scripts/material_bills.csv` and `subindustry_exposure.csv` before
  the fund pitch - they are judgement calls (which materials matter per industry,
  and how much) written by me, not sourced numbers, and disclosed as such in
  `resource_supply_risk.py`'s docstring.

### 2026-09-12 - both indicators rescaled to [0,1]

- Done: `value` in both `resource_supply_risk` and `critical_material_disclosure`
  is now in [0,1] (was 0-100ish and an unbounded sum). Both use a fixed theoretical
  ceiling as the divisor, not the observed min/max, so the scale does not shift
  every quarter as data updates:
  - `resource_supply_risk`: /100 (exposure in [0,1] x basket risk in [0,100]).
  - `critical_material_disclosure`: / (23 tracked materials x 100), i.e. the score
    if a company named every material we track at maximum possible risk.
  Catalog `unit` updated to `risk index 0-1` for both. Ranking of companies is
  unchanged, only the scale - AMD/ADI/AVGO etc. still top `resource_supply_risk` at
  0.5025, NEM still tops `critical_material_disclosure` at 0.3473.
- `python run.py check`: 21 tests pass, format check OK.

