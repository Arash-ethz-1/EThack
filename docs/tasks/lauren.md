# Lauren - economic impact

**Area (as of 2026-09-12):** `economic/`, swapped with Arash by agreement. Arash owns
shared infra (`universe/`, `common/`, `run.py`, `profiles/`, `dashboard/`, `portfolio/`,
`docs/*.md`, `AGENTS.md`) and confirmed the swap himself in `AGENTS.md` and
`docs/tasks/arash.md` (commit `9584788`).
**Goal phase 1:** >= 3 `ready` economic indicators in `economic/catalog.csv`.

Previously on `social/` (society: customers, communities, governance) - dropped that area
entirely as part of the swap. Florian needs a new co-owner for the society half, or to
cover all of `social/` solo. The candidate list below is preserved for whoever picks it up.

Your earlier scoring work (`score.py`, indicator set) is preserved in git history at
commit `1c89ef2` - useful as reference for sector-relative scoring later.

## Getting started (no git knowledge needed)

1. Open the `EThack` folder in Claude Code.
2. Type `/start`. The agent pulls the latest work and tells you where things stand.
3. Tell it what you want in normal words, e.g. *"Let's build the board diversity indicator."*
4. Type `/save` whenever something works, and before you stop.

## Candidate indicators (verify coverage before building)

| id | idea | direction | watch out |
|---|---|---|---|
| `board_gender_diversity` | % women on the board (proxy statement, SEC DEF 14A) | higher better | extraction from text; keep the quote in `note` |
| `consumer_penalties` | consumer-protection / discrimination penalties per $ revenue (e.g. CFPB, FTC enforcement) | lower better | parent-company matching, data licence |
| `product_recalls` | recalls per year (FDA / CPSC recall databases) | lower better | only relevant for some sectors -> coverage |
| `eeo1_disclosure` | does the company publish its EEO-1 workforce diversity report? (1/0) | higher better | binary -> many ties; fine as one of several |

## Needs from others

- Arash: `universe/sp500.csv` and `universe/financials.csv` (blocker for everyone,
  including all 3 economic indicators below - `employment_growth` needs the `employees`
  column specifically)
- Florian: find a co-owner (or take solo) for the `social/` society indicators above

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->

### 2026-09-12 19:32 - area swap
- Done: agreed with Arash to swap areas - I take `economic/`, he keeps `social/` off his
  plate (was never built, catalog still empty). Updated the header above accordingly.
- Next: settle on 3 economic indicator concepts before building anything (see chat -
  proposing systemic/economic-importance framing instead of Arash's tax/R&D/capex list).
- Problems: none yet
- Needs from others: see list above

### 2026-09-12 19:50 - 3 economic indicators scaffolded
- Done: locked in 3 independent economic-impact indicators, added to `economic/catalog.csv`
  (status `idea`, owner lauren) and scaffolded scripts via `python run.py new-indicator economic <id>`:
  - `tax_rate_gap` - statutory (21%) minus effective tax rate, lower_is_better false ->
    `higher_is_better=false`; source SEC XBRL companyfacts
  - `revenue_volatility` - coefficient of variation of YoY revenue growth, trailing 5y,
    `higher_is_better=false`; source SEC XBRL companyfacts
  - `employment_growth` - 3y CAGR of employee headcount, `higher_is_better=true`; source
    `universe/financials.csv` employees column (not built yet - blocked)
- Next: build `universe/sp500.csv` / `financials.csv` dependency with Arash, then fill in
  `build()` for `tax_rate_gap` and `revenue_volatility` first (don't need `employees`)
- Problems: none yet - all 3 still status `idea`, no real data pulled
- Needs from others: see list above
