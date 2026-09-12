# The wow effect. OWNER: Arash.
# Answers: "what happens to our view of this portfolio if a data source disappears?"

from __future__ import annotations

import pandas as pd

from .indicators.registry import all_indicators, surviving


def impact(panel: pd.DataFrame, dead_sources: frozenset[str]) -> dict:
    # Return, for a given blackout scenario:
    #   indicators_lost   which ones stop being computable
    #   companies_dark    tickers that fall below MIN_COVERAGE_TO_RANK
    #   rank_churn        mean absolute rank change, and Kendall tau vs. the full score
    #   ci_widening       mean CI width before vs. after
    # These four numbers ARE the slide. Make them exact.
    raise NotImplementedError


def scenarios() -> dict[str, frozenset[str]]:
    return {
        "Today": frozenset(),
        "GHGRP rescinded": frozenset({"epa_ghgrp"}),
        "GHGRP + ECHO gone": frozenset({"epa_ghgrp", "epa_echo"}),
        "All US federal environmental data gone": frozenset(
            {"epa_ghgrp", "epa_echo"}
        ),
        "Voluntary reporting collapses too": frozenset(
            {"epa_ghgrp", "epa_echo", "company_reports"}
        ),
    }
