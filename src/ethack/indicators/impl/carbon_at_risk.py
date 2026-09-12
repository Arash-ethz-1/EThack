# Carbon earnings at risk. Turns sustainability into a cash-flow number.
# OWNER: Lauren.

from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import CARBON_PRICES
from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class CarbonAtRisk(Indicator):
    spec = IndicatorSpec(
        id="carbon_at_risk_100",
        name="Carbon earnings at risk @ $100/t",
        dimension=Dimension.FINANCIAL,
        durability=Durability.DERIVED,
        sources=("epa_ghgrp", "sec_xbrl"),
        direction=-1,
        unit="fraction of EBITDA",
        rationale=(
            "Price the metered tonnes and charge them against profit. This is the "
            "number a portfolio manager can act on, and it is what makes the framework "
            "investable rather than merely descriptive. Reported at three price points "
            "so the reader can pick their own transition scenario."
        ),
        default_weight=2.0,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        price = CARBON_PRICES[1]
        ebitda = panel["ebitda_usd"].where(panel["ebitda_usd"] > 0)
        out = (panel["metered_scope1_t"] * price) / ebitda
        return out.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
