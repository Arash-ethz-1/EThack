# S&P 500 Sustainability - what we built (state 2026-09-13, morning)

Read this first when you wake up. Numbers below were printed by the code in this repo.

## The product in one sentence

A dashboard that scores all 500 S&P 500 companies on sustainability, builds a
sustainability-tilted index fund from the scores, and proves the score means something.

    python run.py start        # pull everything
    python run.py dashboard    # http://127.0.0.1:8500

## How it flows (redesign 2026-09-13 morning)

1. **Start page** - title, our definition, three weights (Planet / People / Economic base, 0-3), a chip per
   indicator to switch it off, and "Equal" or "Net zero" emphasis. Button: Compute.
2. **Pipeline** - five lines that each run a real server call and show its result and time:
   scores -> $1bn fund -> back to 2021 vs EPA fines -> 1,000 random weightings -> carbon price stress.
3. **Results** - Ranking, Fund, Net zero, Evidence, Method. Minimal look: white, black type,
   hairlines, one typeface; colour only for the three pillars; fund = black, index = grey.

Evidence A and B are **computed live on the chosen weights** (`POST /api/evidence`, same code as
`python run.py verify`). The weight test went from 214 s to ~9 s: ranks are computed once
(`common.score.profile_ranks`) and every weighting is scored with `common.score.total_scores`
(identical numbers, tested).

Deep links for the pitch (they run the pipeline with default weights, then open the tab):
`#netzero`, `#portfolio`, `#evidence/A`, `#evidence/B`, `#evidence/C/NUE`, `#method/NUE`.

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

## Net zero - the bonus question (Net zero tab, portfolio/transition.py)

Answer: **sell the fuel, re-weight the rest, keep the market.** Three funds side by side
(profile net_zero, printed by `python portfolio/transition.py`):

| | Index (equal weight) | Without fossil fuels & tobacco | Net-zero fund |
|---|---|---|---|
| Holdings | 500 | 477 | 477 |
| Carbon intensity (tCO2e/$M) | 138.2 | 136.3 | 79.6 |
| Money with a science-based target | 45.2% | 47.0% | 60.1% |
| Pre-tax profit a $130/t carbon price would take (IEA 2030) | 8.21% | 8.01% | 5.28% |
| same at $250/t (IEA 2050) | 9.92% | 9.30% | 6.30% |

The point for the jury: **excluding oil & gas alone barely changes the direct carbon cost
exposure** (8.21% -> 8.01%); the tilt inside every sector does the work (-> 5.28%).
Method: EPA GHGRP Scope 1 tonnes (US facilities > 25 kt, 2023) x carbon price / SEC pre-tax income of
the same year, capped at 100%, a loss-making emitter counts as 100%. 131 emitters, 3 without income
on record left out. No pass-through, no Scope 2/3 - stated on the page.

## Method tab - the calculation for one company

`POST /api/trace` shows every step with the real numbers: source values with links -> position among
sector peers (dot strip) -> rank formula -> pillar weighted means -> total -> fund weight
(equal weight -> exclusions -> z-score -> tilt factor -> sector rescale -> cap -> dollars of $1bn).

## Evidence (Evidence tab, checks/)

Design rule since the morning pass: few words, big numbers, charts; explanations sit in collapsed
"How it's calculated" rows. **Audit (C)** now shows the company's own most concrete 10-K sentences on
planet / people / lawsuits (keyword-highlighted, from the 10-Ks cached in economic/raw/, < 1 s), its EPA
emissions and penalties as big numbers, and news loaded separately (GDELT still answers HTTP 429 - a news
search button is the fallback).

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
