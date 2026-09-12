# Carbon earnings at risk @ $200/t - the aggressive transition-price scenario.
# OWNER: Lauren. Sibling of carbon_at_risk.py (@ $100/t) and carbon_at_risk_50.py.

from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import CARBON_PRICES
from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class CarbonAtRisk200(Indicator):
    spec = IndicatorSpec(
        id="carbon_at_risk_200",
        name="Carbon earnings at risk @ $200/t",
        dimension=Dimension.FINANCIAL,
        durability=Durability.DERIVED,
        sources=("epa_ghgrp", "sec_xbrl"),
        direction=-1,
        unit="fraction of EBITDA",
        rationale=(
            "The high end of a plausible carbon-price corridor, roughly the EU ETS "
            "range. Names that only look exposed at $200/t are a very different risk "
            "position from names that are already exposed at $50/t - the three price "
            "points together are the point, not any single one of them."
        ),
        default_weight=1.0,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        price = CARBON_PRICES[2]
        ebitda = panel["ebitda_usd"].where(panel["ebitda_usd"] > 0)
        out = (panel["metered_scope1_t"] * price) / ebitda
        return out.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
