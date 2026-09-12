"""EThack dashboard - choose indicators, see scores, explain them. Portfolio is a placeholder.

    python run.py dashboard

All numbers come from common/score.py; this file only shows them and collects the
user's choices (which indicators, which weights) as a Profile.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from common.config import CATEGORIES, DEFAULT_PROFILE, ROOT  # noqa: E402
from common.demo import demo_dataset  # noqa: E402
from common.score import (  # noqa: E402
    Dataset,
    Profile,
    explain,
    list_profiles,
    load_dataset,
    load_profile,
    save_profile,
    score_profile,
    slugify,
)
from portfolio.allocate import OUTPUT_COLUMNS, PLANNED_SETTINGS  # noqa: E402

# categorical slots 1-3 of the reference palette - validated as a set for all pairs
CATEGORY_COLOR = {"economic": "#2a78d6", "social": "#eb6834", "environmental": "#1baf7a"}
SEQUENTIAL = "#2a78d6"
CATEGORY_LABEL = {c: c.capitalize() for c in CATEGORIES}

st.set_page_config(page_title="EThack - S&P 500 impact", page_icon="🌍", layout="wide")


# ---------------------------------------------------------------- data
@st.cache_data(show_spinner=False)
def get_real() -> Dataset:
    return load_dataset()


@st.cache_data(show_spinner=False)
def get_demo() -> Dataset:
    return demo_dataset()


def category_scale() -> alt.Scale:
    return alt.Scale(domain=list(CATEGORY_COLOR), range=list(CATEGORY_COLOR.values()))


# ---------------------------------------------------------------- sidebar: the user's choices
def apply_profile(profile: Profile, data: Dataset) -> None:
    """Copy a saved profile into the widgets."""
    for c in CATEGORIES:
        st.session_state[f"cw_{c}"] = float(profile.category_weights.get(c, 1.0))
    for _, row in data.catalog.iterrows():
        iid = row["indicator_id"]
        w = float(profile.indicator_weights.get(iid, row["weight"]))
        st.session_state[f"on_{iid}"] = w > 0
        st.session_state[f"w_{iid}"] = w if w > 0 else float(row["weight"])
    st.session_state["sector_relative"] = profile.sector_relative
    st.session_state["min_share"] = profile.min_weight_share
    st.session_state["save_name"] = profile.name


def sidebar(data_real: Dataset) -> tuple[Dataset, Profile]:
    sb = st.sidebar
    sb.title("Your priorities")

    has_real = not data_real.catalog.empty
    source = sb.radio(
        "Data",
        ["Real indicators", "Demo (random numbers)"],
        index=0 if has_real else 1,
        help="Real = every `ready` indicator in the repo. Demo = synthetic companies DEMO001... to try the tool.",
    )
    data = data_real if source.startswith("Real") else get_demo()

    names = list_profiles()
    choice = sb.selectbox(
        "Start from profile", names, index=names.index(DEFAULT_PROFILE) if DEFAULT_PROFILE in names else 0
    )
    base = load_profile(choice)
    if st.session_state.get("_loaded") != (choice, source):
        apply_profile(base, data)
        st.session_state["_loaded"] = (choice, source)
    if base.description:
        sb.caption(base.description)
    for msg in base.warnings(data.catalog):
        sb.caption(f"⚠ {msg}")

    sb.subheader("How much each category counts")
    for c in CATEGORIES:
        sb.slider(CATEGORY_LABEL[c], 0.0, 5.0, step=0.5, key=f"cw_{c}")

    sb.subheader("Which indicators count")
    for c in CATEGORIES:
        rows = data.catalog[data.catalog["category"] == c]
        with sb.expander(f"{CATEGORY_LABEL[c]} ({len(rows)})", expanded=len(rows) > 0):
            if rows.empty:
                st.caption("No `ready` indicators yet.")
            for _, row in rows.iterrows():
                iid = row["indicator_id"]
                arrow = "↑ higher is better" if row["higher_is_better"] == "true" else "↓ lower is better"
                on = st.checkbox(row["name"] or iid, key=f"on_{iid}", help=f"{row['description']}\n\n{row['unit']}, {arrow}")
                st.slider("weight", 0.5, 5.0, step=0.5, key=f"w_{iid}", disabled=not on, label_visibility="collapsed")

    sb.subheader("Rules")
    sb.toggle(
        "Compare within sector",
        key="sector_relative",
        help="Rank each company only against its own GICS sector - an oil company is compared to oil companies.",
    )
    sb.slider(
        "Minimum data coverage",
        0.0, 1.0, step=0.05, key="min_share",
        help="A company gets a score only if the indicators it has carry at least this share of the weight.",
    )

    profile = Profile(
        name=st.session_state.get("save_name") or base.name,
        description=base.description,
        category_weights={c: st.session_state[f"cw_{c}"] for c in CATEGORIES},
        indicator_weights={
            iid: (st.session_state[f"w_{iid}"] if st.session_state[f"on_{iid}"] else 0.0)
            for iid in data.catalog["indicator_id"]
        },
        min_weight_share=st.session_state["min_share"],
        sector_relative=st.session_state["sector_relative"],
        portfolio=base.portfolio,
    )

    with sb.expander("Save as profile"):
        st.text_input("Name", key="save_name")
        if st.button("Save", width="stretch"):
            path = save_profile(profile, st.session_state["save_name"])
            st.success(f"saved {path.relative_to(ROOT).as_posix()}")
            if data.demo:
                st.caption("Saved from demo data - demo indicator ids are ignored for real data.")
    return data, profile


# ---------------------------------------------------------------- views
def score_columns() -> dict:
    cfg = {
        "total_score": st.column_config.ProgressColumn("Total", min_value=0, max_value=100, format="%.1f"),
        "position": st.column_config.NumberColumn("#", width="small"),
        "ticker": st.column_config.TextColumn("Ticker", width="small"),
    }
    for c in CATEGORIES:
        cfg[f"{c}_score"] = st.column_config.ProgressColumn(CATEGORY_LABEL[c], min_value=0, max_value=100, format="%.1f")
    return cfg


def view_ranking(result, data: Dataset) -> None:
    table = result.table
    col1, col2 = st.columns([2, 1])
    sectors = sorted(s for s in data.universe["sector"].unique() if s)
    chosen = col1.multiselect("Sectors", sectors, placeholder="all sectors")
    search = col2.text_input("Search ticker or name")
    if chosen:
        table = table[table["sector"].isin(chosen)]
    if search:
        mask = table["ticker"].str.contains(search, case=False) | table["name"].str.contains(search, case=False)
        table = table[mask]

    cols = ["position", "ticker", "name", "sector", "total_score"] + [f"{c}_score" for c in CATEGORIES]
    st.dataframe(table[cols], column_config=score_columns(), hide_index=True, width="stretch", height=420)

    scored = table.dropna(subset=["total_score"])
    if scored.empty:
        return
    left, right = st.columns(2)
    for col, title, part in ((left, "Top 10", scored.head(10)), (right, "Bottom 10", scored.tail(10))):
        chart = (
            alt.Chart(part)
            .mark_bar(color=SEQUENTIAL, cornerRadiusEnd=4, height=14)
            .encode(
                x=alt.X("total_score:Q", title="Total score", scale=alt.Scale(domain=[0, 100])),
                y=alt.Y("ticker:N", sort="-x", title=None),
                tooltip=["ticker", "name", "sector", alt.Tooltip("total_score:Q", format=".1f", title="total")],
            )
            .properties(title=title, height=300)
        )
        col.altair_chart(chart, width="stretch")


def view_company(result, data: Dataset) -> None:
    table = result.table
    if table.empty:
        st.info("No companies yet.")
        return
    labels = {t: f"{t} - {n}" if n else t for t, n in zip(table["ticker"], table["name"])}
    ticker = st.selectbox("Company", list(labels), format_func=labels.get)
    row = table.set_index("ticker").loc[ticker]
    n_scored = int(table["total_score"].notna().sum())

    cols = st.columns(4)
    total = row["total_score"]
    cols[0].metric(
        "Total score",
        "no score" if pd.isna(total) else f"{total:.1f}",
        None if pd.isna(total) else f"#{row['position']} of {n_scored}",
        delta_color="off",
    )
    for col, c in zip(cols[1:], CATEGORIES):
        v = row[f"{c}_score"]
        col.metric(CATEGORY_LABEL[c], "–" if pd.isna(v) else f"{v:.1f}", f"{int(row[f'{c}_n_indicators'])} indicators", delta_color="off")
    if pd.isna(total):
        st.info("Not enough data for a total score under the current coverage rule.")

    detail = explain(data, result, ticker)
    if detail.empty:
        return
    detail["rank_pct"] = detail["rank"] * 100
    detail["label"] = detail["name"].where(detail["name"] != "", detail["indicator_id"])

    st.markdown("**Percentile per indicator** - 100 = best of the compared companies, bar length = where this company stands")
    has = detail.dropna(subset=["rank"])
    chart = (
        alt.Chart(has)
        .mark_bar(cornerRadiusEnd=4, height=14)
        .encode(
            x=alt.X("rank_pct:Q", title="Percentile (100 = best)", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("label:N", title=None, sort=list(has["label"])),
            color=alt.Color("category:N", scale=category_scale(), legend=alt.Legend(orient="top", title=None)),
            tooltip=[
                "label", "category",
                alt.Tooltip("value:Q", format=",.3~f"), "unit", "year",
                alt.Tooltip("rank_pct:Q", format=".0f", title="percentile"),
                alt.Tooltip("points:Q", format=".1f", title="points to total"),
            ],
        )
        .properties(height=max(120, 26 * len(has)))
    )
    st.altair_chart(chart, width="stretch")

    missing = detail[detail["rank"].isna()]
    if not missing.empty:
        st.caption("No data: " + ", ".join(missing["label"]))

    show = detail[["category", "label", "value", "unit", "year", "rank_pct", "weight", "points"]]
    st.dataframe(
        show,
        hide_index=True,
        width="stretch",
        column_config={
            "label": "Indicator",
            "value": st.column_config.NumberColumn("Raw value", format="%.3g"),
            "year": st.column_config.NumberColumn("Year", format="%d"),
            "rank_pct": st.column_config.ProgressColumn("Percentile", min_value=0, max_value=100, format="%.0f"),
            "points": st.column_config.NumberColumn("Points to total", format="%.1f", help="Sums to the total score"),
        },
    )


def view_sectors(result) -> None:
    table = result.table[result.table["sector"] != ""]
    if table.empty:
        st.info("Sectors appear once universe/sp500.csv exists.")
        return
    agg = {"companies": ("ticker", "count"), "scored": ("total_score", "count"), "total_score": ("total_score", "median")}
    agg.update({f"{c}_score": (f"{c}_score", "median") for c in CATEGORIES})
    by_sector = table.groupby("sector").agg(**agg).reset_index().sort_values("total_score", ascending=False)

    st.markdown("**Median score per sector**")
    chart = (
        alt.Chart(by_sector)
        .mark_bar(color=SEQUENTIAL, cornerRadiusEnd=4, height=14)
        .encode(
            x=alt.X("total_score:Q", title="Median total score", scale=alt.Scale(domain=[0, 100])),
            y=alt.Y("sector:N", sort="-x", title=None),
            tooltip=["sector", "companies", "scored", alt.Tooltip("total_score:Q", format=".1f", title="median total")],
        )
        .properties(height=26 * len(by_sector))
    )
    st.altair_chart(chart, width="stretch")
    cfg = score_columns()
    st.dataframe(by_sector, hide_index=True, width="stretch", column_config={**cfg, "sector": "Sector"})
    if not st.session_state.get("sector_relative"):
        st.caption("Big gaps between sectors? Try **Compare within sector** in the sidebar.")


def view_indicators(result, data: Dataset) -> None:
    if data.catalog.empty:
        st.info("No `ready` indicators yet. Switch to demo data in the sidebar to try the tool.")
        return
    n = len(data.universe)
    rows = []
    for _, ind in data.catalog.iterrows():
        iid = ind["indicator_id"]
        values = data.values[iid].dropna() if iid in data.values else pd.Series(dtype=float)
        years = data.years[iid].dropna() if iid in data.years else pd.Series(dtype=float)
        rows.append(
            {
                "category": ind["category"],
                "indicator": ind["name"] or iid,
                "chosen": iid in result.weights.index,
                "weight": result.weights.get(iid, 0.0),
                "direction": "↑ higher better" if ind["higher_is_better"] == "true" else "↓ lower better",
                "unit": ind["unit"],
                "coverage": len(values) / n * 100 if n else 0,
                "companies": len(values),
                "years": f"{int(years.min())}-{int(years.max())}" if len(years) else "",
                "source": ind["source"],
                "owner": ind["owner"],
            }
        )
    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        width="stretch",
        column_config={
            "coverage": st.column_config.ProgressColumn("Coverage %", min_value=0, max_value=100, format="%.0f",
                                                        help="Target: 70% of the universe"),
        },
    )

    chosen = result.ranks.dropna(axis=1, how="all")
    if chosen.shape[1] >= 2:
        st.markdown("**Do two indicators measure the same thing?** Rank correlation between chosen indicators - "
                    "close to +1 means near-duplicates.")
        corr = chosen.corr(method="spearman").round(2)
        corr.index.name = "a"
        long = corr.reset_index().melt(id_vars="a", var_name="b", value_name="rho")
        heat = (
            alt.Chart(long)
            .mark_rect(stroke="white", strokeWidth=2)
            .encode(
                x=alt.X("b:N", title=None, sort=list(corr.columns)),
                y=alt.Y("a:N", title=None, sort=list(corr.columns)),
                color=alt.Color("rho:Q", title="ρ", scale=alt.Scale(domain=[-1, 0, 1], range=["#e34948", "#f0efec", "#2a78d6"])),
                tooltip=["a", "b", alt.Tooltip("rho:Q", format=".2f")],
            )
        )
        text = heat.mark_text(fontSize=11).encode(text=alt.Text("rho:Q", format=".2f"), color=alt.value("#0b0b0b"))
        st.altair_chart((heat + text).properties(height=40 * len(corr) + 40), width="stretch")


def view_portfolio(profile: Profile) -> None:
    st.warning("**Placeholder - phase 3.** Portfolio allocation is not built yet. The method is a team decision (docs/PLAN.md).")
    left, right = st.columns(2)
    with left:
        st.markdown(
            "**What it will do**\n\n"
            "1. Input: the scores of the profile chosen on the left\n"
            "2. Turn scores into weights for a $1B fund (`portfolio/allocate.py`)\n"
            f"3. Output: `{', '.join(OUTPUT_COLUMNS)}`, weights sum to 100%\n\n"
            "**Open decisions**\n"
            "- tilt (overweight high scores) or exclusion (drop the bottom X%)?\n"
            "- start from market-cap weights (needs market cap) or equal weights?\n"
            "- max weight per company, sector-neutral vs. the S&P 500?"
        )
    with right:
        st.markdown("**Settings a profile can already store under `[portfolio]`**")
        st.dataframe(
            pd.DataFrame(
                {"setting": list(PLANNED_SETTINGS), "meaning": list(PLANNED_SETTINGS.values()),
                 "this profile": [str(profile.portfolio.get(k, "")) for k in PLANNED_SETTINGS]}
            ),
            hide_index=True,
            width="stretch",
        )
        st.button("Build portfolio", disabled=True, help="Available in phase 3")


# ---------------------------------------------------------------- page
def main() -> None:
    data, profile = sidebar(get_real())
    result = score_profile(data, profile)

    st.title("Sustainability impact of the S&P 500")
    if data.demo:
        st.error("**DEMO DATA** - companies and numbers are random. Nothing on this page is a real result.")
    elif data.catalog.empty:
        st.info("No `ready` indicators in the repo yet - switch to demo data in the sidebar to try the tool.")

    n = len(data.universe)
    cols = st.columns(4)
    cols[0].metric("Companies with a total score", f"{int(result.table['total_score'].notna().sum())} / {n}")
    for col, c in zip(cols[1:], CATEGORIES):
        k = int(data.catalog.loc[data.catalog["indicator_id"].isin(result.weights.index), "category"].eq(c).sum())
        share = result.category_weights.get(c, 0) / result.category_weights.sum() * 100 if len(result.category_weights) else 0
        col.metric(CATEGORY_LABEL[c], f"{share:.0f}% of total", f"{k} indicators chosen", delta_color="off")

    tabs = st.tabs(["Ranking", "Company", "Sectors", "Indicators", "Portfolio"])
    with tabs[0]:
        view_ranking(result, data)
    with tabs[1]:
        view_company(result, data)
    with tabs[2]:
        view_sectors(result)
    with tabs[3]:
        view_indicators(result, data)
    with tabs[4]:
        view_portfolio(profile)
    st.caption(f"Profile: {profile.name} · scores by common/score.py (percentile ranks, docs/SCORING.md) · "
               f"save it with 'Save as profile' → profiles/{slugify(profile.name)}.toml")


main()
