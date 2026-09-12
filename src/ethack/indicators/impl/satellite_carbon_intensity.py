# Satellite-only carbon intensity. OWNER: Lauren.
#
# The one indicator with NO dependency on any US environmental agency continuing
# to publish anything, and no dependency on a company choosing to disclose. It
# needs a satellite (ESA/Climate TRACE, outside US administrative reach) and a
# revenue figure (SEC XBRL - securities law, not environmental policy).
#
# Without this file, satellite_divergence looked like our blackout-proof
# indicator but actually still names "company_reports" as a source (it compares
# satellite tonnes to the company's OWN disclosure) - kill voluntary reporting and
# it dies too, and the thesis's own worst-case scenario
# ("Voluntary reporting collapses too", see blackout.scenarios()) leaves the
# framework with zero computable indicators. This is what actually survives it.

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class SatelliteCarbonIntensity(Indicator):
    spec = IndicatorSpec(
        id="satellite_carbon_intensity",
        name="Satellite-observed carbon intensity",
        dimension=Dimension.ENVIRONMENTAL,
        durability=Durability.PERMANENT,
        sources=("satellite", "sec_xbrl"),
        direction=-1,
        unit="tCO2e (satellite-observed) / $M revenue",
        rationale=(
            "Emissions inferred from space, per dollar of SEC-mandated revenue. "
            "Neither input requires a US environmental agency to keep publishing or "
            "a company to keep disclosing voluntarily - this is the number that is "
            "still there in the scenario where everything else has gone dark. "
            "Weaker per-company precision than the GHGRP meter, which is the price "
            "of that independence, not a flaw we are hiding."
        ),
        default_weight=1.0,
        min_coverage=0.20,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        obs = panel.get("satellite_scope1_t")
        if obs is None:
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)
        rev_m = panel["revenue_usd"] / 1e6
        out = obs / rev_m.where(rev_m > 0)
        return out.replace([np.inf, -np.inf], np.nan).rename(self.spec.id)
