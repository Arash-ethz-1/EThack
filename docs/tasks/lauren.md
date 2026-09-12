# Lauren - social impact (society)

**Area:** `social/` - shared with Florian. **One indicator = one person:** you only edit
indicators whose `owner` in `social/catalog.csv` is you.
**Goal phase 1:** together with Florian, >= 3 `ready` social indicators. Suggested split:
Florian = **workforce**, Lauren = **society** (customers, communities, governance).
Agree on the split with Florian before building.

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

- Arash: `universe/sp500.csv`

## Log

<!-- append below, never edit old entries. Format: AGENTS.md section 6 -->
