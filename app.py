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

import multivariate as mv
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


@st.cache_data
def run_multivariate(_data, data_key: str, years: tuple | None, exclude: tuple, winsor: float, n_comp: int | None, k: int):
    prep = mv.prepare(_data, list(years) if years else None, list(exclude), winsor)
    pca = mv.run_pca(prep, n_comp)
    return prep, pca, mv.cluster_companies(prep, pca, k), mv.industry_separation(prep)


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

tab_matrix, tab_industry, tab_corr, tab_multi, tab_data = st.tabs(
    ["📋 Company Matrix", "🏭 Industry Stats", "🔗 Ratio Correlations", "🧩 PCA & Clustering", "🧾 Data & Checks"]
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

# ==========================================
# TAB 5: PCA & CLUSTERING
# ==========================================
CLUSTER_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]

with tab_multi:
    st.subheader("🧩 PCA and cluster analysis: all 100 companies")
    st.markdown(
        "Two different questions, answered in order:\n"
        "1. **Grouping the ratios (PCA).** Many of the 25 ratios measure the same thing. PCA reduces them to a "
        "few underlying financial dimensions (*components*) and shows which ratios belong together.\n"
        "2. **Grouping the companies (cluster analysis).** Companies are grouped by how similar their scores on "
        "those components are. The clusters are then compared with the four industries.\n\n"
        "Each company is **one row**: the median of each ratio over the selected years."
    )

    with st.expander("⚙️ Settings (defaults follow standard practice; change only if you have a reason)"):
        s1, s2 = st.columns(2)
        with s1:
            period = st.radio(
                "Years used for each company's profile:",
                [f"Median of all years ({YEARS[0]}–{YEARS[-1]})", f"{selected_year} only"],
                key="mv_period",
            )
            winsor = st.slider(
                "Cap extreme values at percentile (each tail)", 0, 10, 5, key="mv_winsor",
                help="Values beyond this percentile are set to the percentile, so a few outliers cannot dominate PCA.",
            ) / 100
        with s2:
            exclude = st.multiselect(
                "Ratios left out:",
                UNIVERSAL_RATIOS,
                default=list(mv.DEFAULT_EXCLUDED),
                key="mv_exclude",
                help="Left out by default: " + " ".join(f"{r}: {why}" for r, why in mv.DEFAULT_EXCLUDED.items()),
            )
            n_comp_choice = st.selectbox(
                "Number of components:", ["Automatic (eigenvalue > 1)"] + list(range(2, 11)), key="mv_ncomp"
            )
    years_sel = None if period.startswith("Median") else (selected_year,)
    n_comp = None if isinstance(n_comp_choice, str) else int(n_comp_choice)

    k_default = 4
    k = st.session_state.get("mv_k", k_default)
    prep, pca, clus, sep = run_multivariate(data, data_key, years_sel, tuple(exclude), winsor, n_comp, k)
    labels = mv.component_labels(pca)
    comps = list(pca.loadings.columns)

    for note in prep.notes:
        st.caption(f"ℹ️ {note}")
    st.caption(f"{len(prep.z)} companies × {len(prep.ratios)} ratios used.")

    # ---------- Step 1: PCA ----------
    st.markdown("### Step 1 · Grouping the ratios with PCA")
    m1, m2, m3 = st.columns(3)
    m1.metric("Components kept", pca.n_components)
    m2.metric("Variance explained", f"{pca.explained['Cumulative %'].iloc[pca.n_components - 1]:.1f}%")
    m3.metric("Ratios reduced", f"{len(prep.ratios)} → {pca.n_components}")

    scree_col, table_col = st.columns([3, 2])
    with scree_col:
        scree = pca.explained.reset_index(names="Component").head(12)
        scree["Kept"] = scree.index < pca.n_components
        bars = (
            alt.Chart(scree)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("Component:N", sort=None, title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Eigenvalue:Q"),
                color=alt.condition(alt.datum.Kept, alt.value(HIGHLIGHT), alt.value(PEER)),
                tooltip=["Component", alt.Tooltip("Eigenvalue:Q", format=".2f"),
                         alt.Tooltip("% of variance:Q", format=".1f"), alt.Tooltip("Cumulative %:Q", format=".1f")],
            )
        )
        rule = alt.Chart(pd.DataFrame({"y": [1]})).mark_rule(strokeDash=[4, 4], color=NEGATIVE).encode(y="y:Q")
        st.altair_chart((bars + rule).properties(height=300, title="Scree plot"), width="stretch")
        st.caption("Blue = components kept. Dashed line = eigenvalue 1 (a component must explain more than one ratio's worth of variance).")
    with table_col:
        expl = pca.explained.head(pca.n_components).copy()
        expl.insert(0, "Name", [labels[c] for c in expl.index])
        st.dataframe(expl.round(2), width="stretch")

    st.markdown("**Which ratios belong to which component** (varimax-rotated loadings)")
    load_long = pca.loadings.reset_index(names="Ratio").melt("Ratio", var_name="Component", value_name="Loading")
    load_long["Component"] = load_long["Component"].map(lambda c: f"{c}: {labels[c]}")
    heat = (
        alt.Chart(load_long)
        .mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Component:N", sort=None, title=None, axis=alt.Axis(labelAngle=-30, labelLimit=260, labelOverlap=False)),
            y=alt.Y("Ratio:N", sort=list(pca.assignment.index), title=None, axis=alt.Axis(labelLimit=240)),
            color=alt.Color("Loading:Q", scale=alt.Scale(domain=[-1, 0, 1], range=[NEGATIVE, NEUTRAL, POSITIVE], interpolate="lab")),
            tooltip=["Ratio", "Component", alt.Tooltip("Loading:Q", format="+.2f")],
        )
    )
    text = (
        alt.Chart(load_long[load_long["Loading"].abs() >= 0.4])
        .mark_text(fontSize=11)
        .encode(x=alt.X("Component:N", sort=None), y=alt.Y("Ratio:N", sort=list(pca.assignment.index)),
                text=alt.Text("Loading:Q", format=".2f"))
    )
    st.altair_chart((heat + text).properties(height=len(prep.ratios) * 24), width="stretch")
    st.caption("Ratios are sorted by the component they load on most. Numbers shown where |loading| ≥ 0.4.")

    assign = pca.assignment.copy()
    assign["Component"] = assign["Component"].map(lambda c: f"{c}: {labels[c]}")
    assign["Matches textbook?"] = [
        "✓" if cat in comp else "✗" for cat, comp in zip(assign["Textbook category"], assign["Component"])
    ]
    st.dataframe(assign.round(2), width="stretch")
    mismatch = assign[assign["Matches textbook?"] == "✗"]
    st.info(
        f"**{len(assign) - len(mismatch)} of {len(assign)} ratios** group where the textbook puts them. "
        + (
            "Exceptions: " + "; ".join(f"**{r}** ({row['Textbook category']}) behaves like {row['Component'].split(': ', 1)[1]}"
                                     for r, row in mismatch.iterrows()) + "."
            if len(mismatch) else ""
        )
    )

    # ---------- Step 2: clustering ----------
    st.markdown("### Step 2 · Grouping the companies with cluster analysis")
    st.markdown(
        f"k-means clustering on the {pca.n_components} component scores (standardised). "
        "Pick the number of clusters; the silhouette chart shows how well-separated each choice is."
    )
    k_col, sil_col = st.columns([1, 3])
    with k_col:
        st.slider("Number of clusters (k)", 2, 8, k_default, key="mv_k",
                  help="4 lets you compare directly with the 4 industries.")
        best_k = int(clus.silhouette.idxmax())
        st.caption(f"Best-separated choice: **k = {best_k}** (silhouette {clus.silhouette.max():.2f}).")
    with sil_col:
        sil = clus.silhouette.rename_axis("k").reset_index()
        sil["Selected"] = sil["k"] == clus.k
        sil_chart = (
            alt.Chart(sil)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("k:O", title="Number of clusters", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Average silhouette:Q", title="Silhouette"),
                color=alt.condition(alt.datum.Selected, alt.value(HIGHLIGHT), alt.value(PEER)),
                tooltip=["k", alt.Tooltip("Average silhouette:Q", format=".3f")],
            )
        )
        st.altair_chart(sil_chart.properties(height=200), width="stretch")
        st.caption("Silhouette guide: above 0.5 strong, 0.25–0.5 moderate, below 0.25 weak/overlapping clusters.")

    a1, a2, a3 = st.columns(3)
    a1.metric("Clusters", clus.k)
    a2.metric("Match with industries (ARI)", f"{clus.ari_industry:.2f}",
              help="Adjusted Rand Index: 1 = clusters identical to industries, 0 = no better than chance.")
    a3.metric("Agreement with Ward clustering (ARI)", f"{clus.ari_ward:.2f}",
              help="Stability check: the same data clustered with a different method (hierarchical, Ward).")

    plot_df = pca.scores.iloc[:, :2].copy()
    plot_df.columns = ["x", "y"]
    plot_df["Company"] = plot_df.index
    plot_df["Industry"] = prep.industry.reindex(plot_df.index).values
    plot_df["Cluster"] = clus.labels.reindex(plot_df.index).map(lambda c: f"Cluster {c}").values
    domain = [f"Cluster {i}" for i in range(1, clus.k + 1)]
    scatter = (
        alt.Chart(plot_df)
        .mark_point(filled=True, size=90, stroke="white", strokeWidth=1, opacity=0.9)
        .encode(
            x=alt.X("x:Q", title=f"{comps[0]}: {labels[comps[0]]}"),
            y=alt.Y("y:Q", title=f"{comps[1]}: {labels[comps[1]]}"),
            color=alt.Color("Cluster:N", scale=alt.Scale(domain=domain, range=CLUSTER_COLORS[: clus.k]),
                            legend=alt.Legend(orient="right")),
            shape=alt.Shape(
                "Industry:N",
                scale=alt.Scale(domain=industries, range=["circle", "square", "triangle-up", "diamond"][: len(industries)]),
                legend=alt.Legend(orient="right", labelLimit=240),
            ),
            tooltip=["Company", "Industry", "Cluster", alt.Tooltip("x:Q", format=".2f", title=comps[0]),
                     alt.Tooltip("y:Q", format=".2f", title=comps[1])],
        )
    )
    st.altair_chart(scatter.properties(height=460, title="Companies on the first two components"), width="stretch")
    st.caption("Colour = cluster, shape = industry. If clusters matched industries, each colour would have one shape.")

    ct_col, desc_col = st.columns([3, 2])
    with ct_col:
        st.markdown("**Clusters vs industries** (number of companies)")
        ct = clus.crosstab.copy()
        ct.index = [f"Cluster {i}" for i in ct.index]
        ct["Total"] = ct.sum(axis=1)
        st.dataframe(ct, width="stretch")
    with desc_col:
        st.markdown("**What characterises each cluster**")
        for c, text_desc in clus.descriptions.items():
            st.markdown(f"- **Cluster {c}** ({int((clus.labels == c).sum())} cos.): {text_desc}")

    prof = clus.profile_z.copy()
    prof.index = [f"Cluster {i}" for i in prof.index]
    prof_long = prof.reset_index(names="Cluster").melt("Cluster", var_name="Ratio", value_name="z")
    prof_heat = (
        alt.Chart(prof_long)
        .mark_rect(stroke="white", strokeWidth=1)
        .encode(
            x=alt.X("Ratio:N", sort=list(pca.assignment.index), title=None,
                    axis=alt.Axis(labelAngle=-45, labelLimit=200, labelOverlap=False)),
            y=alt.Y("Cluster:N", title=None),
            color=alt.Color("z:Q", scale=alt.Scale(domain=[-1.5, 0, 1.5], range=[NEGATIVE, NEUTRAL, POSITIVE],
                                                   interpolate="lab", clamp=True), title="vs average (sd)"),
            tooltip=["Cluster", "Ratio", alt.Tooltip("z:Q", format="+.2f")],
        )
    )
    st.altair_chart(prof_heat.properties(height=40 * clus.k + 140, title="Cluster profiles"), width="stretch")
    st.caption("Blue = above the all-company average, red = below (in standard deviations).")

    with st.expander("Companies in each cluster"):
        members = pd.DataFrame({"Cluster": clus.labels, "Industry": prep.industry.reindex(clus.labels.index)})
        for c in sorted(members["Cluster"].unique()):
            grp = members[members["Cluster"] == c]
            st.markdown(f"**Cluster {c}** — " + ", ".join(f"{n} ({ind.split()[0]})" for n, ind in grp["Industry"].items()))

    # ---------- Step 3: industry separation ----------
    st.markdown("### Step 3 · Which ratios really separate the industries?")
    st.markdown("Kruskal–Wallis test on each ratio across the 4 industries. **eta²** = share of the ratio's "
                "variation explained by industry (0.01 small, 0.06 medium, 0.14+ large).")
    sep_chart = (
        alt.Chart(sep)
        .mark_bar(cornerRadiusEnd=4, height=12)
        .encode(
            x=alt.X("eta²:Q", title="eta² (variation explained by industry)"),
            y=alt.Y("Ratio:N", sort=None, title=None, axis=alt.Axis(labelLimit=240, labelOverlap=False)),
            color=alt.condition(alt.datum["p-value"] < 0.05, alt.value(HIGHLIGHT), alt.value(PEER)),
            tooltip=["Ratio", alt.Tooltip("eta²:Q", format=".3f"), alt.Tooltip("p-value:Q", format=".4f"),
                     "Highest industry", "Lowest industry"],
        )
    )
    st.altair_chart(sep_chart.properties(height=len(sep) * 22), width="stretch")
    st.caption("Blue = significant difference between industries (p < 0.05).")
    st.dataframe(sep.round(4), hide_index=True, width="stretch")

    # ---------- Downloads / jamovi ----------
    st.markdown("### Reproduce in jamovi")
    out_scores = pca.scores.copy()
    out_scores.columns = [f"{c} {labels[c]}" for c in out_scores.columns]
    export = pd.concat(
        [prep.industry.rename("Industry"), prep.features.round(4), out_scores.round(4), clus.labels.rename("Cluster")],
        axis=1,
    ).rename_axis("Company").reset_index()
    st.download_button("⬇️ PCA input, component scores and clusters (CSV)", export.to_csv(index=False).encode("utf-8"),
                       file_name="pca_cluster_data.csv", mime="text/csv")
    st.markdown(
        "1. Open the CSV in jamovi.\n"
        "2. **Factor → Principal Component Analysis**: add the ratio columns (not the PC or Cluster columns). "
        "Keep *Based on eigenvalue > 1* and *Varimax* rotation. Loadings will match Step 1 (signs may flip).\n"
        "3. **Clustering** (install the *snowCluster* module from the jamovi library): k-means on the PC columns "
        f"with k = {clus.k}. Cluster numbers may be ordered differently, but the groups will be the same or very close.\n"
        "4. **ANOVA → One-Way ANOVA (Non-parametric) / Kruskal–Wallis** on each ratio by Industry reproduces Step 3."
    )
