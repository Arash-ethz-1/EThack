# social/ - what this data is and what it is worth

Seven indicators, six `ready`. This page says what each one actually measures, how good it
is, and where it lies. Numbers below were printed by code in this repo; re-run
`python run.py check` if you want to confirm them.

## The indicators

| indicator | owner | measures | coverage | direction |
|---|---|---|---|---|
| `shareholder_payout_ratio` | Florian | buybacks + dividends as a share of operating cash flow - how much self-generated cash leaves the firm instead of staying available for wages, headcount and capability | **501/503 (100%)** 2016-2025 | lower better |
| `human_capital_disclosure` | Florian | how many quantified workforce facts (headcount, diversity %, turnover, training, safety, pay gap) a company publishes in its 10-K Human Capital section | **500/503 (99%)** | higher better |
| `ceo_pay_ratio` | Arash | CEO pay divided by median employee pay | 479/503 (95%) | lower better |
| `political_alignment` | Florian | corporate PAC money per $M revenue - influence bought over the public rules everyone lives under | 465/503 (92%) 2016-2025 | lower better |
| `employer_retirement_contribution` | Arash | employer retirement contribution per active participant | 464/503 (92%) | higher better |
| `labor_litigation_intensity` | Florian | federal employment-discrimination, wage and labor lawsuits filed against the company, per $bn revenue | 439/503 (87%) 2016-2025 | lower better |
| `workplace_injury_rate` | Arash | recordable injury cases per 100 full-time employees | 328/503 (65%) - **`in_progress`**, below the 70% bar | lower better |

## Quarterly panels (10 years) - read the caveat

`common/score.py` scores one number per company. These panels are extra, for a time series
or a backtest, and live in `social/raw/` because the committed format has no `quarter`
column yet (a proposal is open with Arash).

| panel | rows | tickers | quarters |
|---|---|---|---|
| `political_alignment_panel.csv` | 18,672 | 468 | **40** (2016Q1-2025Q4) |
| `shareholder_payout_panel.csv` | 18,572 | 501 | 40 |
| `labor_litigation_panel.csv` | 15,938 | 439 | 37 |

**Only two of the three are genuinely quarterly.** Litigation and political money are real
dated events bucketed into the quarter they happened in. The payout panel holds the
fiscal-year ratio flat across four quarters, because XBRL cash-flow facts are cumulative
year-to-date - a fiscal-Q2 10-Q carries a six-month duration and never matches a calendar
quarter. Measured: `CY2023Q1` has 403 of our tickers, `CY2023Q2` only 30. Every row says so
in its `note`. Do not claim it moves quarterly.

## What each one gets wrong

Say these before someone else finds them.

- **`labor_litigation_intensity`** measures *disputes that reached federal court*, not
  workplace harm. A company with aggressive mandatory-arbitration clauses keeps cases out
  of court and therefore scores better. Federal employment filings fell ~40% over the
  decade (12,055 in 2016 -> 7,088 in 2024) for exactly that reason; harmless here because
  scoring ranks companies against each other within a period, but it would break if ranks
  were ever pooled across time. Subsidiaries under different names are undercounted -
  Aflac is sued as *American Family Life Assurance Company*, Alphabet as *Google*.
- **`political_alignment`**: 190 of 465 companies sit at exactly 0 because they run no
  federal PAC. That is measured, not imputed - but it means the indicator discriminates
  among ~275 companies and gives the rest a shared best score. It also cannot see
  lobbying fees, trade-association dues, 527s or dark money, so it **structurally rewards
  opacity**: route your influence somewhere we cannot see and you score better.
- **`shareholder_payout_ratio`** is the weakest *social* claim - a judge may fairly call it
  financial. Cash not paid out can go to debt, M&A or hoarding, not to employees. Its
  missingness is also non-random: the "operating cash flow <= 0" rule drops large banks in
  trading-heavy years (BAC, C, GS, JPM all absent in 2024; Financials are 79 of 387 missing
  ticker-years), so those firms must not be treated as neutral.
- **`human_capital_disclosure`** measures *disclosure quality, not workforce outcomes*. A
  company can disclose beautifully and treat people badly. Section-end detection is the
  weak part: in 73/500 sections (14.6%) the boundary overshot by at least a paragraph.

## Where the data comes from

| source | used by | note |
|---|---|---|
| CourtListener bulk dump (4.88 GB) | litigation | the API allows 5 requests/minute = hours; the dump has no limit. `social/scripts/_dockets_bulk.py` |
| FEC bulk files (24 zips, 1.3 GB) | political | parses in 1m52s vs 5+ hours for the API. `social/scripts/_fec_bulk.py` |
| SEC XBRL frames | payout, denominators | one request returns every company for a period - never loop per company |
| SEC 10-K primary documents (2.1 GB) | disclosure | `social/raw/tenk/`, git-ignored |
| SEC `formerNames` | everything text-matched | `social/raw/aliases.csv` |

**`social/raw/aliases.csv` matters more than it looks.** Company names in
`universe/sp500.csv` are display names, not legal names, and 88 companies renamed inside
2016-2026. A 2019 search for "Meta Platforms" finds nothing - it was *Facebook, Inc.* until
2021-10-27. Chesapeake -> Expand Energy, AmerisourceBergen -> Cencora, FleetCor -> Corpay.
Any indicator that matches on company text must join through this table.

Large caches are git-ignored with a rebuild command in `.gitignore`. Everything is
reproducible: `python run.py build social <indicator_id>`.

## Two documents that need review

Neither is mine to merge - both are proposals.

- **`docs/superpowers/plans/2026-09-12-portfolio-allocation.md`** - a task-by-task plan for
  `portfolio/allocate.py` (**Arash's file**): sector-neutral capped multiplicative tilt,
  `benchmark_i * exp(lambda * z_i)`. Adversarially reviewed by executing every code block;
  nine defects found and fixed. Its central rule is that **a company without a score keeps
  its benchmark weight** - never dropped, never treated as worst - so our coverage gaps do
  not silently become investment decisions. **Arash: please read before phase 3.**
- **`docs/superpowers/specs/2026-09-13-eth-endowment-fit.md`** - what an actual ETH
  endowment needs, 37 cited sources. Headline finding: **both tobacco companies rank in our
  top fifth** (Philip Morris 96/503, Altria 98/503), so exclusions must be a separate,
  earlier step than the score tilt - a score cannot express a values-based prohibition. It
  also finds ETH's own binding `Anlagerichtlinien des ETH-Rats` requires sustainability to
  follow *"objektiven Kriterien und ist transparent und nachvollziehbar"*. **Everyone:
  worth reading before the presentation.**

## Open items

- `workplace_injury_rate` is at 65%, below the 70% bar (Arash).
- IBM and Reddit have no `human_capital_disclosure` value: IBM incorporates the section by
  reference into Exhibit 13, Reddit hides it under the heading "Building the Future of the
  Internet at Reddit". Honeywell Aerospace (HONA) has no 10-K at all - a 2026 spin-off.
- `universe/sp500.csv` gives **XOM** as CIK 2115436, a 2026 holdco with zero 10-Ks; real
  Exxon filings are under CIK 34088. Two separate indicators hit this and each worked
  around it locally. **Arash: worth fixing at the source.**
- `common.io.cached_download` writes the full URL into the committed
  `social/raw/_downloads.csv`, so **any API key passed as a query parameter lands in git**.
  Caught twice with the FEC key. **Arash: it should redact `api_key=` / `token=`.**
