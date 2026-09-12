# Arash - pipeline, dashboard + repo infrastructure

**Area:** shared infra (`universe/`, `common/`, `run.py`, `profiles/`, `dashboard/`, `portfolio/`, docs).
**Change 2026-09-12:** Lauren took over `economic/`. The candidate list in section 2 is
kept here as her starting point. Arash builds the pipeline after the indicators:
profiles -> scores -> dashboard -> portfolio.

## 1. Blocker for everyone: `universe/sp500.csv` - do this first

Columns `ticker, name, sector, cik` (see `docs/DATA_FORMAT.md`). Commit the script
that builds it (`universe/build_universe.py`) and the raw download.
Candidate source: the Wikipedia "List of S&P 500 companies" table (has symbol,
GICS sector, CIK); cross-check CIKs against `https://www.sec.gov/files/company_tickers.json`.
Tickers with a dash in some sources (`BRK-B`) become `BRK.B`.

Right after: `universe/financials.csv` with `ticker, year, revenue_usd, employees` -
the shared denominators everyone needs for size-neutral indicators (Jean needs revenue
for every intensity). It is not an indicator and is not scored.

## 2. Economic candidate indicators - now Lauren (verify coverage before building)

Most can come from SEC XBRL company facts:
`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` (needs `SEC_CONTACT_EMAIL` in `.env`).

| id | idea | direction | watch out |
|---|---|---|---|
| `effective_tax_rate` | income tax expense / pre-tax income - contribution to public finances | higher better | negative / tiny pre-tax income gives nonsense - drop those rows |
| `rd_intensity` | R&D expense / revenue - investment in innovation | higher better | banks, retailers report no R&D -> coverage may be < 70% |
| `capex_intensity` | capex / revenue - investment in the real economy | higher better | sector-driven, likely needs sector-relative ranking |
| `revenue_growth_3y` | 3-year revenue CAGR - economic value creation | higher better | M&A jumps |
| `operating_margin` | operating income / revenue - economic resilience | higher better | is it *impact*? argue it in the description or drop it |

XBRL tag names differ between companies (`Revenues`,
`RevenueFromContractWithCustomerExcludingAssessedTax`, ...). Try a list of tags in order.

## 3. Pipeline

- [x] profiles (`profiles/*.toml`), category + total score, explain (`common/score.py`)
- [x] dashboard (`python run.py dashboard`): ranking, company breakdown, sectors, indicators, portfolio placeholder
- [ ] sanity-check real scores once indicators are `ready`, decide sector-relative default
- [ ] phase 3: `portfolio/allocate.py` (needs market cap in `universe/` for a cap-weighted tilt)

## Needs from others

- none yet

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->

### 2026-09-12 21:55 - scoring pipeline + dashboard
- Done: profiles (balanced, net_zero), total score, sector-relative option, explain(); Streamlit dashboard with 5 tabs; portfolio placeholder; `python run.py score [profile]` and `python run.py dashboard`; 21 tests pass
- Next: universe/sp500.csv, then check the dashboard with the first real indicators
- Problems: no real indicators yet - dashboard tested on random demo data (DEMO001...)
- Needs from others: Lauren to confirm she owns `economic/` and update her task file
