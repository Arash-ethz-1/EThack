# Sightline dashboard. OWNER: Arash.
# Pages live in app/pages/ - Streamlit picks them up automatically.
#   1_explorer      Arash
#   2_blackout      Arash   <- the wow demo
#   3_portfolio     Florian
#   4_evaluation    Harprit

from __future__ import annotations

import streamlit as st

from _shared import is_mock, load, mock_banner

st.set_page_config(page_title="Sightline", page_icon=":material/visibility:",
                   layout="wide")

st.title("Sightline")
st.caption(
    "Sustainability intelligence that survives the disappearance of its own sources."
)
mock_banner()

st.markdown(
    '''
US federal environmental and climate disclosure is being rolled back. Datasets that
ESG analytics quietly depend on are being defunded, rescinded or taken offline.

**A European fund should not have its risk visibility depend on American political
weather.** So we do three things no conventional ESG score does:

1. **Score on metered physical reality**, not on what companies say about themselves.
2. **Rate every indicator for durability** - can this source still exist in 12 months?
3. **Let you switch a source off** and watch what it costs you. That is the
   *Blackout* page, and it is the point of the whole exercise.
    '''
)

try:
    scores = load("company_scores")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Companies scored", f"{len(scores):,}")
    c2.metric("Median visibility", f"{scores['visibility'].median():.0%}")
    c3.metric("Below rankable coverage",
              f"{(scores['coverage_ratio'] < 0.30).sum():,}")
    c4.metric("Mean CI width", f"{(scores.ci_high - scores.ci_low).mean():.2f}")
    st.caption(
        "Visibility is how much of a company we can actually observe from sources "
        "that still exist. It is reported alongside every score, never folded into it."
    )
except FileNotFoundError:
    st.info("No data yet. Run `python run.py mocks` to populate the dashboard.")
