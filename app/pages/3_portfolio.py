# The $1B book. OWNER: Florian. Nobody else edits this file.

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import load, mock_banner  # noqa: E402

st.title("The $1B net-zero book")
st.caption("Bonus question: the world commits to net zero tomorrow. Allocate.")
mock_banner()

st.markdown(
    '''
Every other team will answer *overweight renewables, divest fossil fuels*. That is
consensus and it is empirically weak: module prices fell about 90% while module
manufacturers destroyed enormous amounts of capital. Decarbonisation working is not
the same as decarbonisation paying.
    '''
)

# TODO Florian:
#   - sleeve table + allocation bar (35 / 22 / 20 / 13 / 10 is the starting proposal,
#     change it if you can defend the change better)
#   - the visibility-sizing toggle: position size scales with how well we can see
#     the company. This is ours alone - make sure it is visible and explained.
#   - name the zero weights out loud, with reasons
