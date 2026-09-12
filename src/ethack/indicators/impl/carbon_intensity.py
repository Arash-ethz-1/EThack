# Metered carbon intensity. REFERENCE IMPLEMENTATION - copy this shape.
# OWNER: Lauren.

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class MeteredCarbonIntensity(Indicator):
    spec = IndicatorSpec(
        id="metered_carbon_intensity",
        name="Metered carbon intensity",
        dimension=Dimension.ENVIRONMENTAL,
        durability=Durability.AT_RISK,
        sources=("epa_ghgrp", "sec_xbrl"),
        direction=-1,
        unit="tCO2e / $M revenue",
        rationale=(
            "Emissions a federal regulator physically metered, per dollar of revenue "
            "the company reported under securities law. Neither number is the company's "
            "opinion of itself. Rated at_risk because GHGRP reporting is under active "
            "rescission - if it goes, this indicator goes with it."
        ),
        default_weight=2.0,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        rev_m = panel["revenue_usd"] / 1e6
        out = panel["metered_scope1_t"] / rev_m.where(rev_m > 0)
        return out.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
