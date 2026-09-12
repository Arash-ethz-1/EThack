# L6: does any of this work? OWNER: Harprit.
# Out: METRICS.md
#
# This layer is the single biggest differentiator in the project, because almost
# nobody validates. Build the harness against mock scores from hour two so that it
# runs the instant real scores land - if evaluation is genuinely last, it happens at
# 09:00 and gets cut, which is how teams lose their strongest slide.
#
# Test 1 - does the score predict misconduct?
#   Build the score on data through 2021 only. Do bottom-quintile companies incur
#   more EPA enforcement dollars in 2022-2024 than top-quintile? Report the odds
#   ratio, the n, and a p-value. Run the same test on a vendor ESG score as the
#   benchmark. If ours separates and theirs does not, that is the slide.
#
# Test 2 - does the market price it?
#   Event study on carbon-policy dates. Abnormal returns of high- vs low-CaR
#   portfolios in a +/-3 day window. If they do not move, say so: unpriced risk is
#   the more interesting finding and it sets up the portfolio.
#
# Test 3 - OURS ALONE: the information half-life.
#   How stale can the data get before the ranking is wrong? Re-score using only
#   data available as of T-1y, T-2y, T-3y and measure Kendall tau against today.
#   This tells the fund how often they must refresh - and what it costs them when
#   refreshing becomes impossible. It is the quantitative core of the whole thesis.

from __future__ import annotations

import pandas as pd


def enforcement_test(scores: pd.DataFrame, enforcement: pd.DataFrame) -> dict:
    raise NotImplementedError


def event_study(scores: pd.DataFrame, prices: pd.DataFrame, dates: list[str]) -> dict:
    raise NotImplementedError


def information_half_life(panel: pd.DataFrame) -> pd.DataFrame:
    raise NotImplementedError


if __name__ == "__main__":
    print("run make eval")
