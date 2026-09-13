# S&P 500 Sustainability - what we built (state 2026-09-13, night)

Read this first when you wake up. Numbers below were printed by the code in this repo.

## The product in one sentence

A dashboard that scores all 500 S&P 500 companies on sustainability, builds a
sustainability-tilted index fund from the scores, and proves the score means something.

    python run.py start        # pull everything
    python run.py dashboard    # http://127.0.0.1:8500

Deep links for the pitch: `#portfolio`, `#evidence/A`, `#evidence/B`, `#evidence/C/NUE`, `#method`.

## Our definition

> A sustainable company can keep running for decades without wearing down the planet,
> its people, or its own economic base.

Three pillars, one plain question each (shown on the Method tab):

| Pillar | Question |
|---|---|
| Environmental | Is it damaging nature - and does it depend on resources that may run out? |
| Social | Does it treat the people who work for it fairly and safely? |
| Economic | Can it sustain itself and the economy around it? |

We call it a **sustainability-tilted S&P 500 fund**, never an "impact fund" (buying listed
shares does not fund new projects - a finance jury will ask).

## Data - 15 ready indicators

| Pillar | Ready | New tonight |
|---|---|---|
| Economic (5) | tax_rate_gap, revenue_volatility, employment_growth (398/503, was 343), federal_contract_exposure, **median_worker_pay** (361/503) | median worker pay from the SEC pay-ratio disclosure; year bug fixed (no more 2027 rows) |
| Social (6) | labor_litigation_intensity, political_alignment, shareholder_payout_ratio, ceo_pay_ratio, employer_retirement_contribution, human_capital_disclosure | workplace_injury_rate stays in_progress (341/503 - OSHA cannot reach 70%) |
| Environmental (4) | resource_supply_risk, **sbti_climate_target** (503), **ghg_intensity** (500, reworked: real tCO2e per $M revenue), **epa_penalty_intensity** (498) | critical_material_disclosure stays in_progress (226/503) |

## Scoring changes (common/score.py)

- Companies are ranked **within their GICS sector** (a bank is never compared with a steel
  maker). Before: 17 of the top 20 were Financials; now 9 sectors in the top 20.
- Only values from **2022 on** count.
- Share classes (GOOG/GOOGL, FOX/FOXA, NWS/NWSA) count **once**.

## Portfolio (Portfolio tab, portfolio/)

Start from the S&P 500 -> exclude tobacco and oil & gas (6 GICS sub-industries, 23 companies)
-> tilt every weight by the score -> keep each sector's size -> cap 5% per company.
Buttons change method, tilt strength, sector neutrality, benchmark (equal / market cap) and the
fossil exclusion live.

| Equal-weight benchmark | Balanced | Net Zero | Benchmark |
|---|---|---|---|
| Sustainability score | 55.1 | 55.1 (environmental 56.4) | 50.1 |
| Carbon intensity (WACI, tCO2e/$M) | 100.0 | 79.6 | 138.2 |
| Weight with a science-based target | 50.7% | 60.2% | 45.2% |
| Tracking error (36 months) | 1.9% | 1.9% | - |
| Hypothetical return/yr, today's weights on 2023-09..2026-08 | 20.4% | 19.4% | 20.5% |

Market-cap weights exist for 461 of 500 companies (SEC share counts x Yahoo closes); the cap
benchmark is a toggle, equal weight stays the default so nobody drops out.

## Evidence (Evidence tab, checks/)

- **A - Low scores get caught later.** Scores rebuilt with data up to 2021 only; within
  each sector, the worst fifth: 26% fined by the EPA in 2022-2025, best fifth: 8% (3.3x).
  Employee lawsuits: no pattern - and we say so.
- **B - The ranking survives disagreement.** 1,000 random weightings: median rank
  correlation with ours 0.87; 78% of our top 50 stay in the top fifth in >= 80% of runs.
- **C - Audit any company.** Filing quotes behind the numbers, EPA cases and emissions,
  recent news (GDELT; it rate-limited us tonight, a news search link is the fallback).

Old checks (traceability, plausibility, ...) still run with `python run.py verify` as internal QA.

## Open / for the team

- Jury Q&A prep and rehearsal: `docs/PITCH.md`.
- Lauren / Jean: your folders were edited tonight (with Arash's OK) - read the commit
  messages (`git log --oneline -20`).
- GDELT news: retry before the demo; if still blocked, demo the audit on a company and use
  the search link.
- Known limits: US data sources, targets are not emissions, fines partly reflect company size.
