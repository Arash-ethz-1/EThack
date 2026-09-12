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

## Footnote: why these 3 economic indicators

Picked to be three genuinely independent axes of "contribution to the economy," not
three ways of measuring the same thing:

| Indicator | Axis | Why it counts as impact |
|---|---|---|
| `tax_rate_gap` | fiscal contribution | direct, quantifiable contribution to public finances - a company paying further below the 21% federal statutory rate is contributing less, not just being efficient |
| `revenue_volatility` | economic stability | unstable revenue transmits instability downstream to workers, suppliers and tax receipts - a real externality, not just a risk metric for the company itself |
| `employment_growth` | labor market contribution | job creation, the most direct link between a company and the real economy; also nearly free to build once `universe/financials.csv` exists (Arash already collects `employees`) |

Ideas considered and dropped, and why:

- **Systemic importance / financial-system connectedness / disruption-if-gone**
  (first framing floated) - conceptually interesting but failed on data: "financial
  interconnectedness" is only published for the ~30 global systemically important banks
  (it's literally one of the five FSB/Basel G-SIB scoring pillars), not the other ~470
  S&P 500 companies - nowhere near the 70% coverage bar. Direction was also ambiguous:
  high systemic importance reads as a risk (too-big-to-fail, contagion channel) as much
  as a positive impact, which fails the "obvious direction" rule.
- **COGS / revenue** - close to a duplicate of gross margin / `operating_margin`
  (already flagged as "is this impact, or just profitability?" on Arash's original
  list). Sector-driven (a grocer and a software company differ ~60pp for reasons that
  have nothing to do with sustainability), so it would mostly re-derive sector
  membership rather than measure anything about a company's individual impact.
- **R&D intensity / capex intensity** (Arash's original candidates) - not wrong, but
  not independent enough from investment-style metrics judges will see from other
  teams, and R&D specifically risked <70% coverage (banks, retailers, utilities report
  none). Kept as a fallback if `employment_growth` doesn't clear coverage once
  `financials.csv` lands.

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

- Arash: `universe/financials.csv` (`sp500.csv` landed 2026-09-12, commit `e760228`) -
  blocks `employment_growth` specifically, needs the `employees` column
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

### 2026-09-12 20:05 - tax_rate_gap + revenue_volatility build() written and validated
- Done: wrote real `build()` for `tax_rate_gap` and `revenue_volatility` (not stubs) plus a
  shared `economic/scripts/_xbrl.py` helper for SEC XBRL company-facts fetch/parse.
  Validated against real Apple data (CIK 0000320193, no universe.csv needed for the test):
  `tax_rate_gap` returned 17 years (2009-2025), `revenue_volatility` returned real revenue
  2018-2025 ($265.6B -> $416.2B), trailing-6y CV = 1.50. Bumped both to status `in_progress`
  in `economic/catalog.csv`. `python run.py check`: 21 passed, format OK.
- Bug caught + fixed: first version of `_xbrl.py` locked onto the first XBRL tag with any
  data per company and dropped years reported under a later tag - Apple's revenue tag
  changed with ASC 606 (2018), so revenue came back as 1 row instead of 8. Fixed to merge
  across tags per year, priority order.
- Next: once `universe/sp500.csv` lands, run both over the full S&P 500, check coverage
  >= 70%, spot-check 10 companies by hand, then `ready`. Still blocked on `employment_growth`
  (needs `universe/financials.csv` employees column).
- Problems: none blocking - both scripts are complete and tested, just waiting on the universe file
- Needs from others: see list above

### 2026-09-12 20:29 - full S&P 500 build, footnote on indicator choice, raw cache untracked
- Done: ran both indicators over the real `universe/sp500.csv` (503 companies, landed this
  session via Arash, commit `e760228`):
  - `tax_rate_gap`: wrote 6264 rows, 485/503 tickers (96.4%). Per-year coverage 2023:
    432/503 (85.9%), 2024: 445/503 (88.5%) - well over the 70% bar.
  - `revenue_volatility`: wrote 454 rows, 454/503 tickers (90.3%). 439/454 (96.7%) have
    their latest window ending 2022+.
  - Note: `python run.py check`'s coverage warning only looks at the single latest year
    in each file (2027, 1 company - Seagate's fiscal calendar runs ahead of the
    calendar year) and is misleading for a multi-year panel; the real per-year numbers
    above are what matter. Flagging for Arash - this affects any indicator with more
    than one year per company, not just mine.
  - Added a "why these 3" footnote to this file explaining the independent-axes
    reasoning and why the systemic-importance framing, COGS/revenue, and R&D/capex
    intensity were considered and dropped.
  - `economic/raw/` held 500 real SEC companyfacts JSON files, 1.8 GB total (largest
    9.2 MB, under the 20 MB single-file limit but too big in aggregate to push to the
    shared repo). Added `economic/raw/companyfacts_*.json` to `.gitignore` (same
    pattern as Florian's `social/raw/submissions/` precedent) - kept locally, kept the
    tiny `_downloads.csv` provenance log, kept the actual output CSVs. Rebuildable any
    time via `python run.py build economic <id>`.
- Next: spot-check 10 companies by hand against real 10-K filings, then mark both
  `ready`. `employment_growth` still blocked on the `employees` column in
  `universe/financials.csv` (revenue landed this session too, per Jean/Arash's
  `2d0dc5d`, but employees is noted "pending" in that commit).
- Problems: `run.py check`'s coverage check looks at the wrong year for multi-year
  panels (see above) - not blocking, just noting for whoever owns that check.
- Needs from others: see list above
