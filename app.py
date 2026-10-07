"""Streamlit UI for the Cluster & Ratio Analysis Dashboard.

Run with:  streamlit run app.py

Data: put the financials workbook (layout of data/capiq_template.xlsx) at
data/financials.xlsx, set FINANCIALS_PATH, or upload it from the sidebar.
The data/ folder is git-ignored so licensed data never reaches the repo.
"""

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from ratio_engine import (
    RATIO_CATEGORIES,
    RATIO_SPECS,
    UNIVERSAL_RATIOS,
    build_insight_markdown,
    category_scores,
    correlation_matrix,
    correlation_strength,
    cross_industry_medians,
    data_checks,
    default_data_path,
    describe_correlation,
    format_value,
    highlights_for,
    industry_category_summary,
    industry_panel,
    industry_trend,
    load_financials,
    pair_counts,
    peer_percentile,
    peer_snapshot,
    regression_slope,
    style_matrix,
    top_correlations,
)

# Chart colours: diverging blue (positive) <-> red (negative) around a neutral
# grey, blue for the selected company and grey for its peers.
POSITIVE = "#2a78d6"
NEGATIVE = "#e34948"
NEUTRAL = "#f0efec"
HIGHLIGHT = "#2a78d6"
PEER = "#a3a29d"
BAND = "#86b6ef"

# Set page configuration to wide layout for the dashboard matrix
st.set_page_config(page_title="Cluster & Ratio Analysis Dashboard", layout="wide", initial_sidebar_state="collapsed")


@st.cache_data
def load_from_path(path: str, mtime: float):
    return load_financials(path)


@st.cache_data
def load_from_upload(name: str, content: bytes):
    import io

    buf = io.BytesIO(content)
    buf.name = name
    return load_financials(buf)


@st.cache_data
def load_panel(_data, data_key: str, industry: str, year: str | None):
    return industry_panel(_data.pool, industry, year)


# ==========================================
# DATA SOURCE
# ==========================================
with st.sidebar:
    st.header("Data")
    uploaded = st.file_uploader("Financials workbook (.xlsx) or CSV", type=["xlsx", "csv"])
    st.caption("Same layout as data/capiq_template.xlsx (sheet 'Data'). Files stay on this machine.")

env_path = os.environ.get("FINANCIALS_PATH")
local_path = Path(env_path) if env_path else default_data_path()
if uploaded is not None:
    data = load_from_upload(uploaded.name, uploaded.getvalue())
    source_name = uploaded.name
elif local_path is not None and local_path.exists():
    data = load_from_path(str(local_path), local_path.stat().st_mtime)
    source_name = local_path.name
else:
    st.title("📊 Cluster & Financial Ratio Analysis Matrix")
    st.info(
        "No data loaded. Upload your financials workbook in the sidebar, or save it as "
        "`data/financials.xlsx` and reload."
    )
    st.stop()

data_pool = data.pool
YEARS = data.years
data_key = f"{source_name}:{len(data.raw)}"
industries = list(data_pool)
n_companies = sum(len(companies) for companies in data_pool.values())

# ==========================================
# HEADER & CONTROLS
# ==========================================
st.title("📊 High-Density Cluster & Financial Ratio Analysis Matrix")
st.markdown(
    f"Showing **{len(UNIVERSAL_RATIOS)} Universal Ratios** across **{len(YEARS)} fiscal years "
    f"({YEARS[0]}–{YEARS[-1]})** for **{n_companies} listed companies** in {len(industries)} industries, "
    "dynamically isolating the 4 industry-critical metrics."
)
st.caption(f"Source file: {source_name}")
st.divider()

col1, col2, col3 = st.columns(3)
with col1:
    selected_industry = st.selectbox("🎯 Select Industry Cluster Target:", industries)
with col2:
    selected_company = st.selectbox("🏢 Select Company:", list(data_pool[selected_industry]))
with col3:
    selected_year = st.selectbox("📅 Select Anchor Fiscal Year:", YEARS, index=len(YEARS) - 1)

company_df = data_pool[selected_industry][selected_company]
highlight_targets = highlights_for(selected_industry)
peers = peer_snapshot(data_pool, selected_industry, selected_year)
peer_medians = peers.median(axis=1)

tab_matrix, tab_industry, tab_corr, tab_data = st.tabs(
    ["📋 Company Matrix", "🏭 Industry Stats", "🔗 Ratio Correlations", "🧾 Data & Checks"]
)

# ==========================================
# TAB 1: COMPANY MATRIX
# ==========================================
with tab_matrix:
    year_idx = YEARS.index(selected_year)
    prev_year = YEARS[year_idx - 1] if year_idx > 0 else None
    metric_cols = st.columns(len(highlight_targets))
    for col, ratio in zip(metric_cols, highlight_targets):
        value = float(company_df.at[ratio, selected_year])
        delta = None
        if prev_year is not None:
            change = value - float(company_df.at[ratio, prev_year])
            if not pd.isna(change):
                delta = f"{change:+.2f} vs {prev_year}"
        pct = peer_percentile(ratio, value, peers.loc[ratio])
        col.metric(
            ratio,
            format_value(ratio, value),
            delta=delta,
            delta_color="normal" if RATIO_SPECS[ratio].higher_is_better else "inverse",
            help=(
                "Not meaningful for this company-year (see Data & Checks)."
                if pd.isna(pct)
                else f"Peer percentile: {pct:.0f} (better than or equal to {pct:.0f}% of the industry)"
            ),
        )

    left_panel, right_panel = st.columns([5, 3])

    with left_panel:
        st.subheader(f"📋 25-Ratio Complete Horizon Matrix: {selected_company}")
        st.dataframe(style_matrix(company_df, highlight_targets, selected_year), height=920, hide_index=True)
        st.caption("— = not meaningful (e.g. P/E with a loss, ROE with negative equity, no inventory reported).")

    with right_panel:
        st.subheader("⚙️ Cluster Diagnostics & Rationale")
        st.info(build_insight_markdown(selected_industry, company_df, selected_year, peer_medians))

        st.divider()
        st.subheader(f"📈 {len(YEARS)}-Year Target Trend Horizon")

        # The 4 critical drivers, one small chart each since their scales differ
        for ratio in highlight_targets:
            trend = company_df.loc[ratio, YEARS].astype(float).rename(selected_company).to_frame()
            trend["Industry Median"] = industry_trend(data_pool, selected_industry, ratio)["Median"]
            st.caption(f"{ratio} ({RATIO_SPECS[ratio].unit})")
            st.line_chart(trend, height=160, color=[HIGHLIGHT, PEER])

# ==========================================
# TAB 2: INDUSTRY STATS
# ==========================================
with tab_industry:
    st.subheader(f"🏭 {selected_industry}: industry statistics for {selected_year}")
    category = st.radio(
        "Ratio category:", list(RATIO_CATEGORIES), index=list(RATIO_CATEGORIES).index("Profitability"), horizontal=True
    )

    # Distribution of every ratio in the category across the industry's companies
    summary = industry_category_summary(data_pool, selected_industry, category, selected_year)
    summary.insert(0, selected_company, company_df.loc[summary.index, selected_year].astype(float))
    display = summary.astype(object)
    for ratio in display.index:
        for col in display.columns:
            if col not in ("Best Company", "Companies"):
                display.at[ratio, col] = format_value(ratio, summary.at[ratio, col])
    st.markdown(
        f"**{category} distribution across {len(data_pool[selected_industry])} companies** "
        "(P25/P75 = the middle half of the industry; Companies = how many have a meaningful value)"
    )
    st.dataframe(display, width="stretch")

    trend_col, rank_col = st.columns(2)

    with trend_col:
        trend_ratio = st.selectbox("Industry trend for:", RATIO_CATEGORIES[category], key="trend_ratio")
        trend = industry_trend(data_pool, selected_industry, trend_ratio).reset_index()
        trend[selected_company] = company_df.loc[trend_ratio, YEARS].astype(float).values
        unit = RATIO_SPECS[trend_ratio].unit
        base = alt.Chart(trend).encode(x=alt.X("Year:O", title=None, axis=alt.Axis(labelAngle=0)))
        band = base.mark_area(opacity=0.25, color=BAND).encode(
            y=alt.Y("P25:Q", title=f"{trend_ratio} ({unit})", scale=alt.Scale(zero=False)),
            y2="P75:Q",
            tooltip=["Year", alt.Tooltip("P25:Q", format=".2f"), alt.Tooltip("P75:Q", format=".2f")],
        )
        long = trend.melt("Year", value_vars=["Median", selected_company], var_name="Series", value_name="Value")
        lines = (
            alt.Chart(long)
            .mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=60))
            .encode(
                x=alt.X("Year:O", axis=alt.Axis(labelAngle=0)),
                y="Value:Q",
                color=alt.Color(
                    "Series:N",
                    scale=alt.Scale(domain=["Median", selected_company], range=[PEER, HIGHLIGHT]),
                    legend=alt.Legend(orient="bottom", title=None),
                ),
                tooltip=["Year", "Series", alt.Tooltip("Value:Q", format=".2f")],
            )
        )
        st.altair_chart((band + lines).properties(height=340), width="stretch")
        st.caption("Shaded band = industry P25–P75 range; grey = industry median.")

    with rank_col:
        scores = category_scores(data_pool, selected_industry, category, selected_year).rename_axis("Company")
        score_df = scores.reset_index()
        score_df["Selected"] = score_df["Company"] == selected_company
        if score_df["Selected"].any():
            rank = int(score_df.index[score_df["Selected"]][0]) + 1
            rank_text = f"{selected_company} ranks **#{rank} of {len(score_df)}**"
        else:
            rank_text = f"{selected_company} has no {category.lower()} values for {selected_year}"
        st.markdown(f"**{category} score leaderboard** — {rank_text}")
        bars = (
            alt.Chart(score_df)
            .mark_bar(cornerRadiusEnd=4, height=12)
            .encode(
                x=alt.X(scores.name + ":Q", scale=alt.Scale(domain=[0, 100]), title="Score (avg. peer percentile)"),
                y=alt.Y("Company:N", sort=None, title=None, axis=alt.Axis(labelOverlap=False, labelLimit=220)),
                color=alt.condition(alt.datum.Selected, alt.value(HIGHLIGHT), alt.value(PEER)),
                tooltip=["Company", alt.Tooltip(scores.name + ":Q", format=".1f")],
            )
        )
        st.altair_chart(bars.properties(height=max(len(score_df), 1) * 20), width="stretch")
        st.caption(
            "Score = average percentile across the category's ratios, adjusted for direction "
            "(for example, lower debt counts as better)."
        )

    st.markdown(f"**{category}: industry medians compared ({selected_year})**")
    cross = cross_industry_medians(data_pool, category, selected_year)
    cross_display = cross.copy().astype(object)
    for ratio in cross.index:
        for ind in cross.columns:
            cross_display.at[ratio, ind] = format_value(ratio, cross.at[ratio, ind])
    st.dataframe(cross_display, width="stretch")

# ==========================================
# TAB 3: RATIO CORRELATIONS
# ==========================================
with tab_corr:
    st.subheader(f"🔗 How the 25 ratios move together: {selected_industry}")
    c1, c2, c3 = st.columns(3)
    with c1:
        scope = st.radio(
            "Data used:",
            ["All years (company-years)", f"{selected_year} only (companies)"],
            help="All years pools every company in every year (more data, but the same company appears "
            "several times). A single year compares companies at one point in time.",
        )
    with c2:
        method = st.radio(
            "Method:",
            ["Spearman", "Pearson"],
            help="Spearman uses ranks, so a few extreme values cannot dominate it; recommended for real "
            "financial ratios. Pearson measures straight-line relationships and is sensitive to outliers.",
        )
    with c3:
        include_identities = st.toggle(
            "Include pairs linked by formula",
            value=False,
            help="Some ratios are calculated from each other (e.g. DSO = 365 / Receivables Turnover), "
            "so they correlate by construction.",
        )

    panel = load_panel(data, data_key, selected_industry, None if scope.startswith("All") else selected_year)
    corr = correlation_matrix(panel, method.lower())
    counts = pair_counts(panel)
    st.caption(
        f"Up to {len(panel)} observations per pair (blank ratios are skipped pair by pair). r runs from −1 "
        "(always move in opposite directions) through 0 (unrelated) to +1 (always move together). "
        "Correlation shows association, not cause."
    )

    # Heatmap of the full 25 × 25 matrix
    heat = corr.rename_axis("Ratio A").reset_index().melt("Ratio A", var_name="Ratio B", value_name="r")
    heat["n"] = [int(counts.at[a, b]) for a, b in zip(heat["Ratio A"], heat["Ratio B"])]
    heat["Strength"] = heat["r"].map(lambda r: "n/a" if pd.isna(r) else correlation_strength(r))
    heatmap = (
        alt.Chart(heat)
        .mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(
                "Ratio B:N",
                sort=UNIVERSAL_RATIOS,
                title=None,
                axis=alt.Axis(labelAngle=-50, labelLimit=180, labelOverlap=False),
            ),
            y=alt.Y("Ratio A:N", sort=UNIVERSAL_RATIOS, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)),
            color=alt.Color(
                "r:Q",
                scale=alt.Scale(domain=[-1, 0, 1], range=[NEGATIVE, NEUTRAL, POSITIVE], interpolate="lab"),
                legend=alt.Legend(title="r", orient="right"),
            ),
            tooltip=["Ratio A", "Ratio B", alt.Tooltip("r:Q", format="+.2f"), "Strength", "n"],
        )
    )
    st.altair_chart(heatmap.properties(height=720), width="stretch")
    st.caption("Blue = move together, red = move in opposite directions. Hover a cell for the exact value and n.")

    # Strongest relationships, split by direction
    pairs = top_correlations(corr, include_identities, counts)
    pos_col, neg_col = st.columns(2)
    with pos_col:
        st.markdown("**⬆⬆ Strongest: move together**")
        st.dataframe(pairs[pairs["r"] > 0].head(10), hide_index=True, width="stretch")
    with neg_col:
        st.markdown("**⬆⬇ Strongest: move in opposite directions**")
        st.dataframe(pairs[pairs["r"] < 0].head(10), hide_index=True, width="stretch")

    st.divider()

    # Pair explorer
    st.markdown("#### 🔍 Explore one pair: if X goes up, what does Y do?")
    x_col, y_col, o_col = st.columns([2, 2, 1])
    with x_col:
        x_ratio = st.selectbox("X ratio:", UNIVERSAL_RATIOS, index=UNIVERSAL_RATIOS.index("Debt-to-Equity"))
    with y_col:
        y_ratio = st.selectbox("Y ratio:", UNIVERSAL_RATIOS, index=UNIVERSAL_RATIOS.index("Interest Coverage Ratio"))
    with o_col:
        trim = st.toggle(
            "Hide extreme values",
            value=True,
            help="Hides points outside the 2nd–98th percentile of either ratio in the chart and the slope. "
            "The correlation r above always uses all values.",
        )

    r = corr.at[x_ratio, y_ratio]
    st.markdown(describe_correlation(x_ratio, y_ratio, r))

    scatter_df = panel[[x_ratio, y_ratio]].reset_index()
    if x_ratio == y_ratio:
        scatter_df = scatter_df.loc[:, ~scatter_df.columns.duplicated()]
    scatter_df = scatter_df.dropna(subset=list(dict.fromkeys([x_ratio, y_ratio])))
    hidden = 0
    if trim and len(scatter_df) > 10:
        keep = pd.Series(True, index=scatter_df.index)
        for ratio in dict.fromkeys([x_ratio, y_ratio]):
            lo, hi = scatter_df[ratio].quantile([0.02, 0.98])
            keep &= scatter_df[ratio].between(lo, hi)
        hidden = int((~keep).sum())
        scatter_df = scatter_df[keep]

    slope = regression_slope(scatter_df[x_ratio], scatter_df[y_ratio]) if x_ratio != y_ratio else float("nan")
    if not pd.isna(slope) and not pd.isna(r):
        st.markdown(
            f"On average, each **+1 {RATIO_SPECS[x_ratio].unit}** in {x_ratio} goes with "
            f"**{slope:+.2f} {RATIO_SPECS[y_ratio].unit}** in {y_ratio}"
            + (" (extreme values excluded)." if trim else ".")
        )

    scatter_df["Selected"] = scatter_df["Company"] == selected_company
    scatter = (
        alt.Chart(scatter_df)
        .mark_circle(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X(f"{x_ratio}:Q", scale=alt.Scale(zero=False)),
            y=alt.Y(f"{y_ratio}:Q", scale=alt.Scale(zero=False)),
            color=alt.condition(alt.datum.Selected, alt.value(HIGHLIGHT), alt.value(PEER)),
            size=alt.condition(alt.datum.Selected, alt.value(110), alt.value(50)),
            order=alt.Order("Selected:N"),
            tooltip=[
                "Company",
                "Year",
                alt.Tooltip(f"{x_ratio}:Q", format=".2f"),
                alt.Tooltip(f"{y_ratio}:Q", format=".2f"),
            ],
        )
    )
    trend_line = (
        alt.Chart(scatter_df)
        .transform_regression(x_ratio, y_ratio)
        .mark_line(color=NEGATIVE if r < 0 else POSITIVE, strokeWidth=2)
        .encode(x=f"{x_ratio}:Q", y=f"{y_ratio}:Q")
    )
    st.altair_chart((scatter + trend_line).properties(height=420), width="stretch")
    st.caption(
        f"Blue dots = {selected_company}; grey dots = its peers. The line is the best-fit trend."
        + (f" {hidden} extreme points hidden." if hidden else "")
    )

    st.divider()

    # Everything that moves with one ratio
    st.markdown("#### 🧭 What moves with one ratio?")
    focus = st.selectbox(
        "Focus ratio:", UNIVERSAL_RATIOS, index=UNIVERSAL_RATIOS.index(highlight_targets[0]), key="focus_ratio"
    )
    drivers = corr[focus].drop(focus).dropna().rename("r").rename_axis("Ratio").reset_index()
    if drivers.empty:
        st.warning(f"{focus} has too few values in this industry, so it has no correlations.")
    else:
        drivers["Direction"] = drivers["r"].map(lambda v: "Moves together" if v > 0 else "Moves opposite")
        drivers["Strength"] = drivers["r"].map(correlation_strength)
        bar = (
            alt.Chart(drivers)
            .mark_bar(cornerRadiusEnd=4, height=12)
            .encode(
                x=alt.X("r:Q", scale=alt.Scale(domain=[-1, 1]), title=f"Correlation with {focus}"),
                y=alt.Y(
                    "Ratio:N",
                    sort=alt.EncodingSortField("r", order="descending"),
                    title=None,
                    axis=alt.Axis(labelLimit=240, labelOverlap=False),
                ),
                color=alt.Color(
                    "Direction:N",
                    scale=alt.Scale(domain=["Moves together", "Moves opposite"], range=[POSITIVE, NEGATIVE]),
                    legend=alt.Legend(orient="bottom", title=None),
                ),
                tooltip=["Ratio", alt.Tooltip("r:Q", format="+.2f"), "Strength"],
            )
        )
        st.altair_chart(bar.properties(height=len(drivers) * 24), width="stretch")

# ==========================================
# TAB 4: DATA & CHECKS
# ==========================================
with tab_data:
    st.subheader("🧾 Data quality and how the ratios are calculated")
    for issue in data.issues:
        st.markdown(f"- {issue}")

    checks = data_checks(data)
    st.markdown(f"**Values to verify ({len(checks)} company-years).** They are kept as reported; check them at the source.")
    st.dataframe(checks, hide_index=True, width="stretch")

    st.markdown("**Ratio formulas**")
    formulas = pd.DataFrame(
        [{"Category": s.category, "Ratio": name, "Formula": s.formula, "Unit": s.unit} for name, s in RATIO_SPECS.items()]
    )
    st.dataframe(formulas, hide_index=True, width="stretch")

    st.markdown("**Download for jamovi / Excel**")
    d1, d2 = st.columns(2)
    d1.download_button(
        "⬇️ All 25 ratios (CSV, one row per company-year)",
        data.ratios.round(4).to_csv(index=False).encode("utf-8"),
        file_name="ratios_by_company_year.csv",
        mime="text/csv",
    )
    d2.download_button(
        f"⬇️ {selected_industry}, {selected_year} only (CSV)",
        data.ratios[(data.ratios["Industry"] == selected_industry) & (data.ratios["Year"] == selected_year)]
        .round(4)
        .to_csv(index=False)
        .encode("utf-8"),
        file_name=f"ratios_{selected_industry.split()[0].lower()}_{selected_year}.csv",
        mime="text/csv",
    )
    st.caption("Blank cells in the CSV are ratios that are not meaningful for that company-year.")
