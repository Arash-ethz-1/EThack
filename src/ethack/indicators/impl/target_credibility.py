# Target credibility: pledge steepness vs. the slope the meter actually shows.
# OWNER: Lauren. Needs `metered_growth_rate` on the panel - see score.build_panel().

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class TargetCredibility(Indicator):
    spec = IndicatorSpec(
        id="target_credibility",
        name="Target credibility gap",
        dimension=Dimension.GOVERNANCE,
        durability=Durability.DERIVED,
        sources=("epa_ghgrp", "company_reports"),
        direction=-1,
        unit="required annualised reduction rate minus delivered rate (pp/yr)",
        rationale=(
            "A pledge is a promise about a slope, not a level. This compares the "
            "annual reduction rate implied by the company's own target_pct / "
            "target_year against the annual rate the meter has actually recorded. "
            "Positive means the company is behind its own pledge - no vendor checks "
            "this because it requires both a target and an independent trend."
        ),
        default_weight=1.25,
        min_coverage=0.40,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        growth = panel.get("metered_growth_rate")
        target_pct = panel.get("target_pct")
        base_year = panel.get("base_year")
        target_year = panel.get("target_year")
        if (
            growth is None
            or target_pct is None
            or base_year is None
            or target_year is None
        ):
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)

        horizon = target_year.astype("float64") - base_year.astype("float64")
        required = target_pct.astype("float64") / horizon.where(horizon > 0)
        delivered = -pd.Series(growth, index=panel.index).astype("float64")

        valid = required.notna() & delivered.notna()
        gap = (required - delivered).where(valid)
        return gap.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
