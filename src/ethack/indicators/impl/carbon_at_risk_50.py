# Carbon earnings at risk @ $50/t - the conservative transition-price scenario.
# OWNER: Lauren. Sibling of carbon_at_risk.py (@ $100/t) and carbon_at_risk_200.py.

from __future__ import annotations

import numpy as np
import pandas as pd

from ...config import CARBON_PRICES
from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class CarbonAtRisk50(Indicator):
    spec = IndicatorSpec(
        id="carbon_at_risk_50",
        name="Carbon earnings at risk @ $50/t",
        dimension=Dimension.FINANCIAL,
        durability=Durability.DERIVED,
        sources=("epa_ghgrp", "sec_xbrl"),
        direction=-1,
        unit="fraction of EBITDA",
        rationale=(
            "The low end of a plausible carbon-price corridor. If even the "
            "conservative scenario eats a meaningful share of EBITDA, the exposure is "
            "not a modelling artefact of picking an aggressive price - report all three "
            "and let the reader pick their own transition scenario."
        ),
        default_weight=1.0,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        price = CARBON_PRICES[0]
        ebitda = panel["ebitda_usd"].where(panel["ebitda_usd"] > 0)
        out = (panel["metered_scope1_t"] * price) / ebitda
        return out.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
