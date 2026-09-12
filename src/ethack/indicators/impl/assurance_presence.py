# Assurance presence: did anyone independent check the company's own number?
# OWNER: Lauren.

from __future__ import annotations

import numpy as np
import pandas as pd

from ..base import Dimension, Durability, Indicator, IndicatorSpec
from ..registry import register


@register
class AssurancePresence(Indicator):
    spec = IndicatorSpec(
        id="assurance_presence",
        name="Third-party assurance",
        dimension=Dimension.GOVERNANCE,
        durability=Durability.VOLUNTARY,
        sources=("company_reports",),
        direction=1,
        unit="1 = assured by a named third party, 0 = self-reported, unassured",
        rationale=(
            "An unaudited number is a claim; an assured one has at least been checked "
            "by someone with liability for being wrong. Rated voluntary because the "
            "company decides whether to pay for assurance at all, and whether to keep "
            "disclosing in the first place - this indicator vanishes if they stop."
        ),
        default_weight=0.75,
        min_coverage=0.30,
    )

    def compute(self, panel: pd.DataFrame) -> pd.Series:
        reported = panel["reported_scope1_t"]
        assurance = panel.get("assurance_provider")
        if assurance is None:
            return pd.Series(np.nan, index=panel.index, name=self.spec.id)
        out = pd.Series(np.nan, index=panel.index, dtype="float64")
        has_report = reported.notna()
        out[has_report] = assurance[has_report].notna().astype("float64")
        return out.rename(self.spec.id)
