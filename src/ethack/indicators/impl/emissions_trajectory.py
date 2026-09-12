# Emissions trajectory 2019-2023: is the metered number actually going down?
# OWNER: Lauren. Needs `metered_growth_rate` on the panel - see score.build_panel().

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class EmissionsTrajectory(Indicator):
    spec = IndicatorSpec(
        id="emissions_trajectory",
        name="Emissions trajectory 2019-2023",
        dimension=Dimension.ENVIRONMENTAL,
        durability=Durability.AT_RISK,
        sources=("epa_ghgrp",),
        direction=-1,
        unit="annualised log-linear growth rate of metered Scope 1, 2019-2023",
        rationale=(
            "A snapshot intensity number rewards companies that were always small "
            "emitters and says nothing about direction of travel. This is the slope of "
            "the metered five-year panel itself - not a self-reported trend line, so it "
            "cannot be restated. Rated at_risk because it inherits GHGRP's exposure: "
            "no meter history, no slope."
        ),
        default_weight=1.5,
        min_coverage=0.40,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        out = panel.get("metered_growth_rate")
        if out is None:
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)
        return pd.Series(out, index=panel.index).rename(self.spec.id)
