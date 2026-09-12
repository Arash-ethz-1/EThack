# The Say-Do gap: what they reported vs. what the meter said.
# OWNER: Lauren. This is our headline indicator - make it airtight.

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class SayDoGap(Indicator):
    spec = IndicatorSpec(
        id="saydo_gap",
        name="Say-Do gap",
        dimension=Dimension.CREDIBILITY,
        durability=Durability.DERIVED,
        sources=("epa_ghgrp", "company_reports"),
        direction=-1,
        unit="fraction of metered emissions unaccounted for in disclosure",
        rationale=(
            "Positive values mean the meter recorded more than the company disclosed. "
            "This is a credibility discount and, under any future disclosure regime, a "
            "liability. No commercial ESG vendor publishes it, because doing so requires "
            "joining facility-level regulatory data to corporate parents - which is the "
            "hard part we did."
        ),
        default_weight=1.5,
        min_coverage=0.50,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        metered = panel["metered_scope1_t"]
        reported = panel["reported_scope1_t"]
        # Only meaningful where we have BOTH, and where the metered figure is
        # material. Comparing a 500t facility to a global disclosure is noise.
        valid = metered.notna() & reported.notna() & (metered > 10_000)
        gap = (metered - reported) / metered.where(metered > 0)
        return (
            gap.where(valid)
            .replace([np.inf, -np.inf], np.nan)
            .rename(self.spec.id)
        )
