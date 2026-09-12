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
