# Does any of this work? OWNER: Harprit. Nobody else edits this file.

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _shared import load, mock_banner  # noqa: E402

st.title("Validation")
st.caption("A score that has never been tested is an opinion with a spreadsheet attached.")
mock_banner()

# TODO Harprit:
#   tab 1  out-of-sample enforcement test: odds ratio, n, p-value, vs. a vendor score
#   tab 2  event study on carbon-policy dates, +/-3 day abnormal returns
#   tab 3  information half-life - Kendall tau vs. data age. This is the one that is
#          ours alone and it is the quantitative core of the thesis.
