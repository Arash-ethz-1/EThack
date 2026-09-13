# portfolio/ - phase 3, owner: Arash

Turns a profile's scores into portfolio weights.

    python run.py portfolio [profile]     -> scores/<profile>/portfolio.csv

`allocate(scores, profile)` -> `ticker, weight, reason` (weights sum to 1). The CSV adds
name, sector, total score and USD for a 1 bn fund. Deterministic code, no model calls.

Method (proposal by Florian, `docs/superpowers/plans/2026-09-12-portfolio-allocation.md`):
equal-weight benchmark -> tilt by z-score of the total score (`exp(tilt_strength * z)`)
or exclude the worst X% -> each sector back to its benchmark weight -> cap per company.
Companies without a score keep their benchmark weight. Reasoning in `allocate.py`.

Settings under `[portfolio]` in `profiles/<name>.toml` (missing ones use the defaults):

| setting | default | meaning |
|---|---|---|
| `method` | `tilt` | `tilt` or `exclude` |
| `tilt_strength` | `0.6` | 0 = benchmark; 0.6 = a company one std better gets 1.8x its weight |
| `exclude_bottom_pct` | `0.1` | `exclude` only: drop the worst 10% of scored companies |
| `max_weight` | `0.05` | cap per company |
| `sector_neutral` | `true` | every GICS sector keeps its benchmark weight |

Also: `exclude_sub_industries` (list of exact GICS sub-industries, weight 0 before the tilt,
reason per company) and `benchmark = "equal" | "cap"`. Share classes of one company (same
CIK) are one holding - the voting class (GOOGL, FOX, NWS).

- `portfolio/marketdata.py` - SEC share counts x Yahoo monthly closes -> market caps
  (461 of 500 companies at 2026-08) and monthly returns. Rebuild: `python portfolio/marketdata.py`.
- `portfolio/risk.py` - today's weights on the last 36 months of returns: tracking error,
  volatility, hypothetical growth. Not a backtest (look-ahead, today's members only).
- `summary()["climate"]` - weighted carbon intensity (WACI) and the share of weight with a
  science-based target, fund vs benchmark: the net-zero answer in two numbers.
- `portfolio/transition.py` - the bonus question (net zero tomorrow, $1bn): index vs
  exclusion-only vs net-zero fund, and a carbon price stress test - share of pre-tax profit a
  carbon bill would take (EPA GHGRP Scope 1 tonnes x price / SEC pre-tax income), $0-250/t with the
  IEA Net Zero 2030/2050 prices marked. `python portfolio/transition.py` prints the table.
- `allocate(..., steps={})` hands back every intermediate weight (benchmark, eligible, z, tilted,
  sector-neutral, capped) - the Method tab shows them for one company.
- Dashboard: Fund tab (`dashboard/static/portfolio.js`, `POST /api/portfolio`), Net zero tab
  (`dashboard/static/netzero.js`, `POST /api/netzero`).

Open: a point-in-time backtest (most indicators only start in 2022+), float-adjusted caps.
