"""Streamlit UI for the Cluster & Ratio Analysis Dashboard.

Run with:  streamlit run app.py
"""

import streamlit as st

from ratio_engine import (
    INDUSTRY_HIGHLIGHTS,
    RATIO_SPECS,
    UNIVERSAL_RATIOS,
    YEARS,
    build_insight_markdown,
    format_value,
    generate_dataset,
    peer_percentile,
    peer_snapshot,
    style_matrix,
)

# Set page configuration to wide layout for the dashboard matrix
st.set_page_config(page_title="Cluster & Ratio Analysis Dashboard", layout="wide")


@st.cache_data
def load_dataset():
    return generate_dataset()


data_pool = load_dataset()
n_companies = sum(len(companies) for companies in data_pool.values())

# ==========================================
# DASHBOARD LAYOUT & RENDERING
# ==========================================
st.title("📊 High-Density Cluster & Financial Ratio Analysis Matrix")
st.markdown(
    f"Showing **{len(UNIVERSAL_RATIOS)} Universal Ratios** across **{len(YEARS)} years** for "
    f"**{n_companies} simulated companies**, dynamically isolating the 4 industry-critical metrics."
)
st.divider()

# Top Controls Toolbar
col1, col2, col3 = st.columns(3)
with col1:
    selected_industry = st.selectbox("🎯 Select Industry Cluster Target:", list(INDUSTRY_HIGHLIGHTS))
with col2:
    selected_company = st.selectbox("🏢 Select Peer Profile:", list(data_pool[selected_industry]))
with col3:
    selected_year = st.selectbox("📅 Select Anchor Analysis Year:", YEARS, index=len(YEARS) - 1)

# Fetch data snapshot
company_df = data_pool[selected_industry][selected_company]
highlight_targets = INDUSTRY_HIGHLIGHTS[selected_industry]
peers = peer_snapshot(data_pool, selected_industry, selected_year)
peer_medians = peers.median(axis=1)

# Driver scorecards for the anchor year
year_idx = YEARS.index(selected_year)
prev_year = YEARS[year_idx - 1] if year_idx > 0 else None
metric_cols = st.columns(len(highlight_targets))
for col, ratio in zip(metric_cols, highlight_targets):
    value = float(company_df.at[ratio, selected_year])
    delta = None
    if prev_year is not None:
        change = value - float(company_df.at[ratio, prev_year])
        delta = f"{change:+.2f} vs {prev_year}"
    pct = peer_percentile(ratio, value, peers.loc[ratio])
    col.metric(
        ratio,
        format_value(ratio, value),
        delta=delta,
        delta_color="normal" if RATIO_SPECS[ratio].higher_is_better else "inverse",
        help=f"Peer percentile: {pct:.0f} (better than or equal to {pct:.0f}% of the cluster)",
    )

# Dashboard Main splits
left_panel, right_panel = st.columns([5, 3])

with left_panel:
    st.subheader(f"📋 25-Ratio Complete Horizon Matrix: {selected_company}")
    st.dataframe(style_matrix(company_df, highlight_targets, selected_year), height=920, hide_index=True)

with right_panel:
    # Render the dynamic insights reasoning box right next to the matrix
    st.subheader("⚙️ Cluster Diagnostics & Rationale")
    st.info(build_insight_markdown(selected_industry, company_df, selected_year, peer_medians))

    st.divider()
    st.subheader("📈 10-Year Target Trend Horizon")

    # The 4 critical drivers, one small chart each since their scales differ
    for ratio in highlight_targets:
        trend = company_df.loc[ratio, YEARS].rename(selected_company).to_frame()
        trend["Cluster Median"] = [
            peer_snapshot(data_pool, selected_industry, y).loc[ratio].median() for y in YEARS
        ]
        st.caption(f"{ratio} ({RATIO_SPECS[ratio].unit})")
        st.line_chart(trend, height=160)
