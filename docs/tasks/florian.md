# Florian - social impact (workforce)

**Area:** `social/` - shared with Lauren. **One indicator = one person:** you only edit
indicators whose `owner` in `social/catalog.csv` is you.
**Goal phase 1:** together with Lauren, >= 3 `ready` social indicators. Suggested split:
Florian = **workforce** (how a company treats its employees), Lauren = **society**
(customers, communities, governance). Agree on the split with Lauren before building.

## Getting started (no git knowledge needed)

1. Open the `EThack` folder in Claude Code.
2. Type `/start`. The agent pulls the latest work and tells you where things stand.
3. Tell it what you want in normal words, e.g. *"Let's build the CEO pay ratio indicator."*
4. Type `/save` whenever something works, and before you stop.

## Candidate indicators (verify coverage before building)

| id | idea | direction | watch out |
|---|---|---|---|
| `ceo_pay_ratio` | CEO pay / median employee pay, mandatory in the proxy statement (SEC DEF 14A) since 2018 | lower better | text in PDFs/HTML -> extraction; keep the quote in `note`, spot-check by hand |
| `injury_rate` | work injuries per 100 employees, OSHA Injury Tracking Application data | lower better | data is per establishment -> must be mapped to the parent company |
| `labor_violation_penalties` | wage/safety/discrimination penalties per $ revenue (e.g. Violation Tracker, OSHA/WHD enforcement data) | lower better | check the data licence and whether parent-company matching exists |
| `employee_growth` | change in headcount over 3 years (10-K) | higher better | M&A jumps |

## Needs from others

- Arash: `universe/sp500.csv`

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->
