"""Streamlit app: PCA of financial ratios and cluster analysis of companies.

Run with:  streamlit run app.py

Data: put the financials workbook (layout of data/capiq_template.xlsx) at
data/financials.xlsx, set FINANCIALS_PATH, or upload it from the sidebar.
The data/ folder is git-ignored so licensed data never reaches the repo.
"""

import io
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

import multivariate as mv
from ratio_engine import RATIO_SPECS, UNIVERSAL_RATIOS, default_data_path, load_financials

# Colours: blue = selected / kept, grey = other; categorical slots for clusters.
HIGHLIGHT = "#2a78d6"
PEER = "#a3a29d"
REFERENCE = "#e34948"
CLUSTER_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SHAPES = ["circle", "square", "triangle-up", "diamond", "cross", "triangle-down"]

st.set_page_config(page_title="PCA & Cluster Analysis of Financial Ratios", layout="wide", initial_sidebar_state="collapsed")


def fmt(ratio: str, value: float) -> str:
    if pd.isna(value):
        return "—"
    unit = RATIO_SPECS[ratio].unit
    return f"{value:.2f}%" if unit == "%" else f"{value:.1f}d" if unit == "days" else f"{value:.2f}x"


@st.cache_data
def load_from_path(path: str, mtime: float):
    return load_financials(path)


@st.cache_data
def load_from_upload(name: str, content: bytes):
    buf = io.BytesIO(content)
    buf.name = name
    return load_financials(buf)


@st.cache_data
def run_analysis(_data, data_key: str, years: tuple | None, exclude: tuple, winsor: float, n_comp: int | None, k: int):
    prep = mv.prepare(_data, list(years) if years else None, list(exclude), winsor)
    pca = mv.run_pca(prep, n_comp)
    return prep, pca, mv.cluster_companies(prep, pca, k), mv.industry_separation(prep)


# ==========================================
# DATA
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
    st.title("🧩 PCA & Cluster Analysis of Financial Ratios")
    st.info(
        "No data loaded. Upload your financials workbook in the sidebar, or save it as "
        "`data/financials.xlsx` and reload."
    )
    st.stop()

YEARS = data.years
data_key = f"{source_name}:{len(data.raw)}"
n_companies = data.raw["Company"].nunique()
industries = list(dict.fromkeys(data.raw["Industry"]))

# ==========================================
# HEADER & SETTINGS
# ==========================================
st.title("🧩 PCA & Cluster Analysis of Financial Ratios")
st.markdown(
    f"**{n_companies} companies** in {len(industries)} industries, {len(UNIVERSAL_RATIOS)} ratios, "
    f"fiscal years {YEARS[0]}–{YEARS[-1]}. Two questions, answered in order:\n"
    "1. **Grouping the ratios (PCA).** Many ratios measure the same thing. PCA reduces them to a few "
    "underlying financial dimensions (*components*) and shows which ratios belong together.\n"
    "2. **Grouping the companies (cluster analysis).** Companies are grouped by their scores on those "
    "components, and the clusters are compared with the industries.\n\n"
    "Each company is **one row**: the median of each ratio over the selected years."
)
st.caption(f"Source file: {source_name}")

with st.expander("⚙️ Settings (defaults follow standard practice; change only if you have a reason)"):
    s1, s2 = st.columns(2)
    with s1:
        period = st.selectbox("Years used for each company's profile:", ["All years (median)"] + YEARS[::-1], key="period")
        winsor = st.slider(
            "Cap extreme values at percentile (each tail)", 0, 10, 5, key="winsor",
            help="Values beyond this percentile are set to the percentile, so a few outliers cannot dominate PCA.",
        ) / 100
    with s2:
        exclude = st.multiselect(
            "Ratios left out:", UNIVERSAL_RATIOS, default=list(mv.DEFAULT_EXCLUDED), key="exclude",
            help=" ".join(f"{r}: {why}" for r, why in mv.DEFAULT_EXCLUDED.items()),
        )
        n_comp_choice = st.selectbox("Number of components:", ["Automatic (eigenvalue > 1)"] + list(range(2, 11)), key="ncomp")
years_sel = None if period.startswith("All") else (period,)
n_comp = None if isinstance(n_comp_choice, str) else int(n_comp_choice)

k = st.session_state.get("k", 4)
prep, pca, clus, sep = run_analysis(data, data_key, years_sel, tuple(exclude), winsor, n_comp, k)
labels = mv.component_labels(pca)
comps = list(pca.loadings.columns)

for note in data.issues + prep.notes:
    st.caption(f"ℹ️ {note}")
st.caption(f"{len(prep.z)} companies × {len(prep.ratios)} ratios used.")

# ==========================================
# STEP 1: PCA — GROUPING THE RATIOS
# ==========================================
st.markdown("## Step 1 · Grouping the ratios with PCA")
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
    rule = alt.Chart(pd.DataFrame({"y": [1]})).mark_rule(strokeDash=[4, 4], color=REFERENCE).encode(y="y:Q")
    st.altair_chart((bars + rule).properties(height=300, title="Scree plot"), width="stretch")
    st.caption("Blue = components kept. Dashed line = eigenvalue 1 (a component must explain more than one ratio's worth of variance).")
with table_col:
    expl = pca.explained.head(pca.n_components).copy()
    expl.insert(0, "Name", [labels[c] for c in expl.index])
    st.dataframe(expl.round(2), width="stretch")

st.markdown("**Component loadings** (varimax-rotated; loadings below 0.40 hidden for readability)")
loadings = pca.loadings.loc[pca.assignment.index].copy()
shown = loadings.map(lambda v: f"{v:+.2f}" if abs(v) >= 0.4 else "")
shown.columns = [f"{c}: {labels[c]}" for c in loadings.columns]
shown["Textbook category"] = pca.assignment["Textbook category"]
shown["Matches textbook?"] = [
    "✓" if cat in labels[comp] else "✗" for cat, comp in zip(pca.assignment["Textbook category"], pca.assignment["Component"])
]
shown["Communality"] = pca.assignment["Communality"].round(2)
st.dataframe(shown, width="stretch", height=len(shown) * 35 + 40)
st.caption("Each ratio is listed under the component it loads on most. Communality = share of the ratio's variance the kept components explain.")

mismatch = shown[shown["Matches textbook?"] == "✗"]
st.info(
    f"**{len(shown) - len(mismatch)} of {len(shown)} ratios** group where the textbook puts them."
    + (
        " Exceptions: "
        + "; ".join(
            f"**{r}** ({shown.at[r, 'Textbook category']}) behaves like {labels[pca.assignment.at[r, 'Component']]}"
            for r in mismatch.index
        )
        + "."
        if len(mismatch)
        else ""
    )
)

# ==========================================
# STEP 2: CLUSTER ANALYSIS — GROUPING THE COMPANIES
# ==========================================
st.markdown("## Step 2 · Grouping the companies with cluster analysis")
st.markdown(
    f"k-means clustering on the {pca.n_components} component scores. Pick the number of clusters; "
    "the silhouette chart shows how well-separated each choice is."
)
k_col, sil_col = st.columns([1, 3])
with k_col:
    st.slider("Number of clusters (k)", 2, 8, 4, key="k", help=f"{len(industries)} lets you compare directly with the industries.")
    st.caption(f"Best-separated choice: **k = {int(clus.silhouette.idxmax())}** (silhouette {clus.silhouette.max():.2f}).")
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
scatter = (
    alt.Chart(plot_df)
    .mark_point(filled=True, size=90, stroke="white", strokeWidth=1, opacity=0.9)
    .encode(
        x=alt.X("x:Q", title=f"{comps[0]}: {labels[comps[0]]}"),
        y=alt.Y("y:Q", title=f"{comps[1]}: {labels[comps[1]]}"),
        color=alt.Color("Cluster:N", scale=alt.Scale(domain=[f"Cluster {i}" for i in range(1, clus.k + 1)],
                                                     range=CLUSTER_COLORS[: clus.k])),
        shape=alt.Shape("Industry:N", scale=alt.Scale(domain=industries, range=SHAPES[: len(industries)]),
                        legend=alt.Legend(labelLimit=240)),
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
    for c, desc in clus.descriptions.items():
        st.markdown(f"- **Cluster {c}** ({int((clus.labels == c).sum())} companies): {desc}")

st.markdown("**Cluster profiles** (median of each ratio)")
prof = clus.profile_median.T.copy()
prof.columns = [f"Cluster {c}" for c in prof.columns]
prof["All companies"] = prep.profiles[prep.ratios].median()
prof = prof.loc[pca.assignment.index]
st.dataframe(prof.apply(lambda col: [fmt(r, v) for r, v in col.items()]), width="stretch", height=len(prof) * 35 + 40)

with st.expander("Companies in each cluster"):
    members = pd.DataFrame({"Cluster": clus.labels, "Industry": prep.industry.reindex(clus.labels.index)})
    for c in sorted(members["Cluster"].unique()):
        grp = members[members["Cluster"] == c]
        st.markdown(f"**Cluster {c}** — " + ", ".join(f"{n} ({ind.split()[0]})" for n, ind in grp["Industry"].items()))

# ==========================================
# STEP 3: WHICH RATIOS SEPARATE THE INDUSTRIES
# ==========================================
st.markdown("## Step 3 · Which ratios really separate the industries?")
st.markdown("Kruskal–Wallis test on each ratio across the industries. **eta²** = share of the ratio's "
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

# ==========================================
# REPRODUCE IN JAMOVI
# ==========================================
st.markdown("## Reproduce in jamovi")
out_scores = pca.scores.copy()
out_scores.columns = [f"{c} {labels[c]}" for c in out_scores.columns]
export = pd.concat(
    [prep.industry.rename("Industry"), prep.features.round(4), out_scores.round(4), clus.labels.rename("Cluster")], axis=1
).rename_axis("Company").reset_index()
d1, d2 = st.columns(2)
d1.download_button("⬇️ PCA input, component scores and clusters (CSV)", export.to_csv(index=False).encode("utf-8"),
                   file_name="pca_cluster_data.csv", mime="text/csv")
d2.download_button("⬇️ All 25 ratios by company-year (CSV)", data.ratios.round(4).to_csv(index=False).encode("utf-8"),
                   file_name="ratios_by_company_year.csv", mime="text/csv")
st.markdown(
    "1. Open `pca_cluster_data.csv` in jamovi.\n"
    "2. **Factor → Principal Component Analysis**: add the ratio columns (not the PC or Cluster columns). "
    "Keep *Based on eigenvalue > 1* and *Varimax* rotation. Loadings will match Step 1 (signs may flip).\n"
    "3. **Clustering** (install the *snowCluster* module from the jamovi library): k-means on the PC columns "
    f"with k = {clus.k}. Cluster numbers may be ordered differently, but the groups will be the same or very close.\n"
    "4. **ANOVA → One-Way ANOVA (Non-parametric)** on each ratio by Industry reproduces Step 3."
)
