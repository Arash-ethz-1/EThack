"""Phase 3 - PLACEHOLDER: turns a profile's scores into portfolio weights.

Not implemented yet. The interface is fixed so the dashboard and run.py can already
call it; the method is a team decision (docs/PLAN.md, phase 3):
- tilt (overweight high scores) vs. exclusion (drop the bottom X%)
- starting point: S&P 500 market-cap weights (needs market cap in universe/) or equal weights
- constraints: max weight per company, sector neutrality vs. the S&P 500

Weights must come from deterministic code, like scores.
"""

from __future__ import annotations

import pandas as pd

from common.score import Profile

OUTPUT_COLUMNS = ["ticker", "weight", "reason"]  # weights sum to 1

# Settings a profile can already put under [portfolio]; read by allocate() once it exists.
PLANNED_SETTINGS = {
    "method": "tilt | exclude",
    "exclude_bottom_pct": "drop the worst X% by total score (method = exclude)",
    "tilt_strength": "how strongly scores shift weight away from the benchmark (method = tilt)",
    "max_weight": "cap per company, e.g. 0.05",
    "sector_neutral": "keep sector weights equal to the S&P 500",
}


def allocate(scores: pd.DataFrame, profile: Profile, fund_usd: float = 1e9) -> pd.DataFrame:
    """scores: Result.table from common.score.score_profile. Returns OUTPUT_COLUMNS."""
    raise NotImplementedError("portfolio allocation is phase 3 - method not decided yet (docs/PLAN.md)")
