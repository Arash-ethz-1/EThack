# Indicator explorer - the flexible-indicator UI. OWNER: Arash.
#
# The controls on this page are GENERATED FROM THE REGISTRY. Lauren adds a file in
# indicators/impl/ and it shows up here with no UI work. That is the whole point of
# the plugin pattern: the fund can pick its own indicator set, not ours.

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import load, mock_banner  # noqa: E402

from ethack.indicators.registry import all_indicators, by_dimension  # noqa: E402

st.title("Indicator explorer")
st.caption("Choose your own indicator set. Weights are yours, and so is the blame.")
mock_banner()

st.sidebar.header("Indicators")
mode = st.sidebar.radio(
    "Weighting",
    ["Declared defaults", "Equal weight", "Confidence-weighted"],
    help=(
        "Confidence-weighted scales each indicator by coverage x durability, so an "
        "indicator whose source may vanish next year carries less of the score."
    ),
)

chosen: dict[str, float] = {}
for dim, inds in by_dimension().items():
    st.sidebar.subheader(dim.title())
    for ind in inds:
        s = ind.spec
        on = st.sidebar.checkbox(s.name, value=True, key=f"on_{s.id}")
        if on:
            wt = st.sidebar.slider(
                f"weight - {s.name}", 0.0, 3.0, float(s.default_weight), 0.1,
                key=f"w_{s.id}",
                disabled=(mode != "Declared defaults"),
            )
            chosen[s.id] = wt

st.subheader("What you selected")
st.dataframe(
    pd.DataFrame([
        {
            "indicator": i.spec.name,
            "dimension": i.spec.dimension.value,
            "durability": i.spec.durability.value,
            "direction": "lower is better" if i.spec.direction < 0 else "higher is better",
            "unit": i.spec.unit,
            "sources": ", ".join(i.spec.sources),
            "weight": chosen.get(i.spec.id),
            "why it is here": i.spec.rationale,
        }
        for i in all_indicators() if i.spec.id in chosen
    ]),
    use_container_width=True, hide_index=True,
)

st.info(
    "Every indicator carries a written rationale and a durability rating. An "
    "indicator we cannot justify in one sentence does not belong in the framework.",
    icon=":material/info:",
)

# TODO Arash: wire score.score(panel, weights=chosen, mode=...) and render the
# ranked table with CI error bars + the equal-weight robustness comparison.
