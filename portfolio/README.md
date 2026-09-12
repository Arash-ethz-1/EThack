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

Open: market-cap benchmark (needs market caps in `universe/`; `benchmark_weights` already
accepts them), dashboard "Build portfolio" button, backtest.
