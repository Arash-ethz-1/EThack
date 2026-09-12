# Facility concentration: how much of the metered footprint sits in one asset.
# OWNER: Lauren. Needs `top_facility_share` on the panel - see score.build_panel().

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class FacilityConcentration(Indicator):
    spec = IndicatorSpec(
        id="facility_concentration",
        name="Facility concentration",
        dimension=Dimension.OPERATIONAL,
        durability=Durability.AT_RISK,
        sources=("epa_ghgrp",),
        direction=-1,
        unit="share of metered US Scope 1 from the single largest facility",
        rationale=(
            "A company whose emissions sit in one plant carries single-asset "
            "transition and stranding risk that a company with the same total spread "
            "across fifty sites does not, even at identical intensity. Concentration is "
            "a physical fact the GHGRP facility list gives us for free."
        ),
        default_weight=0.75,
        min_coverage=0.30,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        out = panel.get("top_facility_share")
        if out is None:
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)
        return pd.Series(out, index=panel.index).rename(self.spec.id)
