# L4: indicators -> scores. OWNER: Lauren.
# In:  the joined company panel
# Out: company_scores
#
# Non-negotiables, because these are what we are judged on:
#   * sector-relative percentiles - comparing software to cement is a category error
#   * bootstrap CIs, and companies whose intervals overlap SHARE a tier.
#     We refuse to claim #47 differs from #63 when the data cannot tell.
#   * a `visibility` column: how much of this company we can actually see
#   * run equal weights too, and report how little the ranking moves. Robustness
#     to your own weighting scheme is the answer when a judge attacks the weights.

from __future__ import annotations

import pandas as pd

from .indicators.registry import surviving


def build_panel() -> pd.DataFrame:
    raise NotImplementedError


def score(
    panel: pd.DataFrame,
    weights: dict[str, float] | None = None,
    dead_sources: frozenset[str] = frozenset(),
    mode: str = "declared",   # declared | equal | confidence
) -> pd.DataFrame:
    # `dead_sources` is what makes the blackout simulator work: drop the indicators
    # that depend on a switched-off source, renormalise the surviving weights, and
    # recompute. Confidence intervals widen on their own as coverage falls, which is
    # the honest behaviour and also the demo.
    indicators = surviving(dead_sources)
    raise NotImplementedError


if __name__ == "__main__":
    print("run make score")
