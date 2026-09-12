# Arash - economic impact + repo infrastructure

**Area:** `economic/`, plus shared infra (`universe/`, `common/`, `run.py`, `portfolio/`, docs).
**Goal phase 1:** >= 3 `ready` economic indicators in `economic/catalog.csv`.

## 1. Blocker for everyone: `universe/sp500.csv` - do this first

Columns `ticker, name, sector, cik` (see `docs/DATA_FORMAT.md`). Commit the script
that builds it (`universe/build_universe.py`) and the raw download.
Candidate source: the Wikipedia "List of S&P 500 companies" table (has symbol,
GICS sector, CIK); cross-check CIKs against `https://www.sec.gov/files/company_tickers.json`.
Tickers with a dash in some sources (`BRK-B`) become `BRK.B`.

Right after: `universe/financials.csv` with `ticker, year, revenue_usd, employees` -
the shared denominators everyone needs for size-neutral indicators (Jean needs revenue
for every intensity). It is not an indicator and is not scored.

## 2. Candidate indicators (verify coverage before building)

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

## 3. Later

- Phase 2: sanity-check real scores, decide sector-relative ranking (`docs/SCORING.md`).
- Phase 3: `portfolio/` allocation.

## Needs from others

- none yet

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->
