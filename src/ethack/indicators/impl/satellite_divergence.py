# Satellite vs. self-report divergence. The indicator that survives a blackout.
# OWNER: Lauren. Coordinate with Jean on the satellite contract before building.

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class SatelliteDivergence(Indicator):
    spec = IndicatorSpec(
        id="satellite_divergence",
        name="Satellite-vs-disclosure divergence",
        dimension=Dimension.CREDIBILITY,
        durability=Durability.PERMANENT,
        sources=("satellite", "company_reports"),
        direction=-1,
        unit="log ratio of observed to disclosed emissions",
        rationale=(
            "The only emissions signal no administration can rescind. Weaker per-company "
            "precision than a meter, but it cannot be defunded, and for a European fund "
            "that continuity is worth more than the precision it gives up. This is the "
            "indicator that keeps working when the others are switched off."
        ),
        default_weight=1.0,
        min_coverage=0.20,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        obs = panel.get("satellite_scope1_t")
        if obs is None:
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)
        rep = panel["reported_scope1_t"]
        valid = obs.notna() & rep.notna() & (obs > 0) & (rep > 0)
        out = np.log(obs.where(valid) / rep.where(valid))
        return pd.Series(out, index=panel.index).rename(self.spec.id)
