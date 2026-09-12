# Plan

**Goal:** quantify the sustainability impact of S&P 500 companies in three categories,
and use it to weight a portfolio allocation.

## Phase 1 - Data extraction (now)

| Category | Owner | Folder |
|---|---|---|
| Economic impact | Lauren | `economic/` |
| Social impact | Florian, Lauren, Arash | `social/` |
| Environmental impact | Jean | `environmental/` |

**Done when**, for every category:
- [ ] `universe/sp500.csv` exists (Arash - blocks the ticker check for everyone)
- [ ] >= 3 indicators with status `ready` in the catalog (strong = criteria in `AGENTS.md` section 4)
- [ ] every indicator reproducible with `python run.py build <category>`
- [ ] `python run.py check` passes with no errors

Suggested order for each person:
1. Pick 4-5 candidate indicators, add them with `python run.py new-indicator` (status `idea`).
2. For each: find the source, check coverage fast (how many S&P 500 companies?). Drop weak ones early.
3. Build the best 3 to `ready`. A 4th/5th is a bonus, not a requirement.

## Phase 2 - Profiles, scores, dashboard (Arash)

The user of the tool (a fund, an investor) decides which indicators count and how much.
That choice is a **profile** (`profiles/<name>.toml`). `python run.py score <profile>` ->
`scores/<profile>/scores.csv`: a 0-100 score per category and a total score.
`python run.py dashboard` does the same interactively and explains every score.
Method in `docs/SCORING.md`. Built and tested on demo data; real scores appear as soon
as indicators are `ready`.

**Done when:** all three categories scored for >= 70% of the universe, and the team
has looked at the top/bottom 10 per category and agrees they make sense.

## Phase 3 - Portfolio allocation

`python run.py portfolio [profile]` -> `scores/<profile>/portfolio.csv` (method in
`portfolio/README.md`): equal-weight benchmark, exp tilt on the total score, companies
without a score held at benchmark, sector-neutral, 5% cap per company. Built and tested.
`profiles/net_zero.toml` answers the bonus question.

## Status 2026-09-13 and next steps

Ready indicators: economic 4 (`tax_rate_gap`, `revenue_volatility`, `employment_growth`,
`federal_contract_exposure`), social 6, **environmental 1** (`resource_supply_risk`, which
has one value per GICS sub-industry, not per company). The environmental score is not
meaningful until the steps below are done. Decisions behind them: see the log (2026-09-13).

### A. Net zero indicator `sbti_climate_target` (environmental) - top priority
- **Source:** SBTi Target Dashboard, companies file
  `https://files.sciencebasedtargets.org/production/files/companies-excel.xlsx` (2.3 MB,
  15,605 organisations; columns incl. `company_name, isin, lei, near_term_status,
  near_term_target_classification, near_term_target_year, net_zero_status, net_zero_year,
  date_updated`). Found via `https://sciencebasedtargets.org/target-dashboard`.
- **Read xlsx without a new dependency:** it is a zip; parse `xl/sharedStrings.xml` +
  `xl/worksheets/sheet1.xml` with `zipfile` + `xml.etree` (cell refs like `C12` -> column).
  Dates are Excel serials (days since 1899-12-30).
- **Match to tickers:** ISIN -> ticker via OpenFIGI (`POST https://api.openfigi.com/v3/mapping`,
  `{"idType": "ID_ISIN", "idValue": ..., "exchCode": "US"}`, no key, 25 requests/min x 10
  ISINs; tested: AAPL, MSFT, ACN resolve). Cache the mapping in `environmental/raw/`.
  Fallback for rows without ISIN: exact normalised SEC name (`social/scripts/_company_match.py`).
  Name matching alone found 245 S&P 500 companies in a first test.
- **Value (ordinal, higher is better):** 4 = net-zero target validated (`net_zero_status =
  Targets set`); 3 = near-term target set, 1.5°C; 2 = near-term target set, well-below 2°C /
  2°C; 1 = committed only; 0 = not on the dashboard or `Commitment removed`. Several rows
  per company (subsidiaries): take the highest. A company not on the dashboard gets 0 with
  `note` "not listed on SBTi dashboard on <date>" - absence is the observation, so coverage
  is 503/503. **Spot-check** the zeros of 20 large companies by hand before `ready`.
- Caveat for the catalog: measures the ambition and credibility of targets, not actual
  emissions.

### B. Scoring changes (`common/score.py`, Arash)
- **Only values from 2022 on count** (`min_year = 2022` in the profile, default in
  `common/config.py`). An older latest value becomes a gap, not a score. Affects e.g.
  `revenue_volatility` (15 companies, oldest 2014) and `tax_rate_gap` (8). Add a test.
- **`sector_relative = true`** in `balanced.toml` and `net_zero.toml`.
- `profile_to_toml` must write lists (needed for the exclusion list below).

### C. Portfolio exclusions (`portfolio/allocate.py`, Arash)
- New `[portfolio]` setting `exclude_sub_industries` (list). `universe/sp500.csv` now has a
  `sub_industry` column (GICS Sub-Industry), done.
- Default list for `balanced`: `Tobacco` (2), `Integrated Oil & Gas` (2), `Oil & Gas
  Exploration & Production` (9), `Oil & Gas Refining & Marketing` (3), `Oil & Gas
  Equipment & Services` (3), `Oil & Gas Storage & Transportation` (4), `Coal & Consumable
  Fuels` (0 today). Weapons: `Aerospace & Defense` (13) bundles Boeing/GE with Lockheed -
  decide whether to include it; controversial-weapons lists (SVVK-ASIR) are not in the repo.
- Order: benchmark -> policy exclusion (weight 0) -> tilt -> sector-neutral -> cap.
  **Bug to avoid:** the whole Energy sector is the 21 Oil & Gas names. Sector neutralisation
  must use the benchmark *after* exclusions, otherwise an emptied sector falls back to
  benchmark weights and re-admits the excluded companies. Add a test for exactly this.
- `reason` column: "excluded: GICS sub-industry X (a classification, not a revenue test)".

### D. Still open (team)
- **Market caps** for a real S&P 500 benchmark (active share, tracking error). No source
  in the repo yet.
- **`ghg_intensity` (Jean):** actual emissions; EPA GHGRP only covers ~100 companies. Keep
  `in_progress` or find a broader emissions source.
- **`federal_contract_exposure`** now sits in economic; Jean and Lauren to confirm owner.
- **`shareholder_payout_ratio` direction** (lower = socially better) - confirm as a team.
- **`min_weight_share`:** 0.5 now; Florian's ETH spec suggests 0.6 (re-check the cliff).
- **Norm-based exclusions** (UN Global Compact violators) - every ETH manager uses them; we
  have no controversy data.
- **XOM:** SEC now maps XOM to the new holding CIK 0002115436 (no filings yet); history is
  under 0000034088, so XOM is missing in most indicators.
- Profile `eth_endowment.toml` as proposed in
  `docs/superpowers/specs/2026-09-13-eth-endowment-fit.md`.

## Decisions log

| Date | Decision |
|---|---|
| 2026-09-12 | Repo reset. New plan: three categories, >= 3 indicators each, 0-100 scores, then portfolio. |
| 2026-09-12 | Scores on a 0-100 scale; percentile-rank method v1 (docs/SCORING.md). |
| 2026-09-12 | Everyone works on `main` with small commits via `python run.py save`; folder ownership prevents conflicts. |
| 2026-09-12 | Lauren takes over `economic/`. Arash builds the rest of the pipeline: profiles, scoring, dashboard, portfolio placeholder. |
| 2026-09-12 | Users choose indicators + weights in a profile; total score = weighted mean of category scores. Dashboard: own web UI (`dashboard/static/`) on a stdlib Python server - no new dependency; the Workspace tab runs every `run.py` command. |
| 2026-09-12 | Task files (`docs/tasks/`) removed - everyone knows their work; progress = catalog `status` + commit messages. |
| 2026-09-13 | Portfolio method: sector-neutral exp tilt on the total score (Florian's plan), unscored companies at benchmark, 5% cap. |
| 2026-09-13 | `federal_contract_exposure` moved from environmental to economic - it measures revenue dependence on the federal budget, not environmental impact. |
| 2026-09-13 | Net zero source: **SBTi Target Dashboard** (validated targets, ISIN-matched). Rejected: Net Zero Tracker (data only embedded in the website's JavaScript, fragile), SBTi + Net Zero Tracker together (both measure targets - duplicate). |
| 2026-09-13 | Ranking **within GICS sector** (`sector_relative = true`) - absolute ranking gave Financials +8 and Utilities -12 points just for their sector. |
| 2026-09-13 | **Only values from 2022 on** count in the score. |
| 2026-09-13 | Portfolio = **tilt + exclusions** by GICS sub-industry (tobacco, oil & gas, coal). |
