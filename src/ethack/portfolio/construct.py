# L5: the $1B book. OWNER: Florian.
# In:  company_scores (+ prices)
# Out: portfolio
#
# Build this against mock scores from the first hour. You are never blocked.
#
# Our differentiated answer to the bonus question - do not lose these:
#   * BOTTLENECK, NOT THEME. A crash net-zero is a wiring problem, not a solar
#     problem. Grid equipment, transformers, copper, regulated utilities with
#     rate-base growth have backlogs and pricing power; module makers are commodity
#     manufacturers whose prices fell ~90% while shareholders were destroyed.
#   * OWN AND ENGAGE, DO NOT DIVEST. Selling a high emitter to someone who does not
#     care removes zero molecules and removes your vote. Hold top-decile emitters
#     whose METERED trajectory is actually falling, and buy the forced-seller discount.
#   * SIZE BY VISIBILITY. This is ours alone: position size scales with how well we
#     can see the company. Low data visibility -> smaller position. Falls straight
#     out of the thesis and no other team will have it.
#   * GREENFLATION. A mandated crash transition is the largest capex programme in
#     history against binding physical constraints - it is inflationary, which
#     derates the long-duration growth names most funds hold as their climate sleeve.
#     So the book is short-duration, hard-asset, value-tilted.
#   * Name the zero weights out loud, with the reason.

from __future__ import annotations

import pandas as pd


def construct(scores: pd.DataFrame, visibility_sizing: bool = True) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print("run python run.py portfolio")
