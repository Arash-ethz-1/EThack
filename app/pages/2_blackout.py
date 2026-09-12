# THE WOW DEMO. OWNER: Arash.
#
# Fifteen seconds, one toggle, and the judges understand the entire project:
# switch off a data source and watch the framework lose its sight.
#
# Four numbers must appear, exact and honest:
#   indicators lost | companies gone dark | rank churn (Kendall tau) | CI widening

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import load, mock_banner  # noqa: E402

from ethack.blackout import scenarios  # noqa: E402
from ethack.indicators.registry import all_indicators, surviving  # noqa: E402

st.title("Blackout simulator")
st.caption(
    "What happens to your view of this portfolio when a data source stops existing?"
)
mock_banner()

names = list(scenarios())
pick = st.select_slider("Scenario", options=names, value=names[0])
dead = scenarios()[pick]

alive = surviving(dead)
lost = [i for i in all_indicators() if i not in alive]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Indicators still computable", f"{len(alive)} / {len(all_indicators())}",
          delta=(-len(lost) if lost else None))
c2.metric("Companies gone dark", "-", help="below minimum rankable coverage")
c3.metric("Rank churn (Kendall tau)", "-")
c4.metric("Mean CI widening", "-")

if lost:
    st.error(
        "**Lost in this scenario:** "
        + ", ".join(i.spec.name for i in lost),
        icon=":material/visibility_off:",
    )
st.success(
    "**Survives regardless:** "
    + ", ".join(i.spec.name for i in alive
                if i.spec.durability.value in ("permanent", "statutory")),
    icon=":material/shield:",
)

st.markdown(
    '''
### Why this is the product

A conventional ESG score does not change when its inputs disappear - it keeps
printing a number, and the number silently stops meaning what it used to mean.
Absence of data looks identical to good performance.

Sightline makes the loss visible and prices it. That is the difference between a
rating and a risk system.
    '''
)

# TODO Arash: wire blackout.impact(panel, dead) to fill the four metrics, and show
# the before/after ranked list side by side with CI error bars.
