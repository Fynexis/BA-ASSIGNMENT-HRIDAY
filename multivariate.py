"""PCA on the ratios and cluster analysis of the companies.

Two different questions, answered in sequence:

1. Grouping the RATIOS (variables): many of the 25 ratios measure the same
   thing. Principal component analysis on their correlation matrix reduces
   them to a few underlying financial dimensions (Pinches et al., 1973;
   Chen & Shimerda, 1981). Each ratio is assigned to the component it
   loads on most strongly.
2. Grouping the COMPANIES (observations): k-means on the component scores
   puts companies with similar financial profiles together, and the
   clusters are compared with the four industries (Gupta & Huefner, 1972).

Each company is one row: the median of each ratio over the chosen years.
Choices follow what jamovi/SPSS do by default (standardised variables,
eigenvalue > 1, varimax rotation) so results can be reproduced there from
the exported input file.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import kruskal
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score

from ratio_engine import RATIO_SPECS, UNIVERSAL_RATIOS, FinancialData

# Ratios left out of PCA/clustering by default, with the reason.
DEFAULT_EXCLUDED: dict[str, str] = {
    "Inventory Turnover": "Undefined for most IT companies (no inventory) and extreme where inventory is tiny.",
    "Days Inventory Outstanding (DIO)": "Same problem as Inventory Turnover (365 / Inventory Turnover).",
    "Receivables Turnover": "Duplicate of DSO (DSO = 365 / Receivables Turnover); keeping both double-counts it.",
    "Equity Multiplier": "Near-duplicate of Debt-to-Equity (both measure balance-sheet leverage).",
}
RANDOM_STATE = 0


@dataclass
class PreparedData:
    profiles: pd.DataFrame  # company × ratio, median over the years (before cleaning)
    features: pd.DataFrame  # company × ratio, imputed + winsorised (in ratio units)
    z: pd.DataFrame  # standardised features (mean 0, sd 1) used for PCA
    industry: pd.Series  # company → industry
    ratios: list[str]
    notes: list[str] = field(default_factory=list)


def company_profiles(data: FinancialData, years: list[str] | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """One row per company: median of each ratio over ``years`` (all years if None)."""
    r = data.ratios if years is None else data.ratios[data.ratios["Year"].isin(years)]
    profiles = r.groupby("Company", sort=False)[UNIVERSAL_RATIOS].median()
    industry = r.groupby("Company", sort=False)["Industry"].first()
    return profiles, industry


def prepare(
    data: FinancialData,
    years: list[str] | None = None,
    exclude: list[str] | None = None,
    winsor: float = 0.05,
) -> PreparedData:
    """Company profiles → choose ratios → fill gaps → limit outliers → standardise."""
    profiles, industry = company_profiles(data, years)
    exclude = list(DEFAULT_EXCLUDED) if exclude is None else exclude
    ratios = [r for r in UNIVERSAL_RATIOS if r not in exclude]
    notes = []

    feats = profiles[ratios].copy()
    missing = feats.isna().sum()
    missing = missing[missing > 0]
    if len(missing):
        # Fill with the company's own industry median, else the overall median
        ind_median = feats.groupby(industry).transform("median")
        feats = feats.fillna(ind_median).fillna(feats.median())
        notes.append(
            "Filled missing values with the industry median: "
            + ", ".join(f"{r} ({n})" for r, n in missing.items())
            + "."
        )
    if winsor > 0:
        lo, hi = feats.quantile(winsor), feats.quantile(1 - winsor)
        clipped = int(((feats < lo) | (feats > hi)).sum().sum())
        feats = feats.clip(lo, hi, axis=1)
        notes.append(
            f"Limited extreme values to the {winsor:.0%}–{1 - winsor:.0%} percentile range of each ratio "
            f"({clipped} values capped), so a few outliers cannot dominate."
        )
    constant = [c for c in feats.columns if feats[c].std() == 0]
    if constant:
        feats = feats.drop(columns=constant)
        ratios = [r for r in ratios if r not in constant]
        notes.append(f"Dropped ratios with no variation: {', '.join(constant)}.")
    z = (feats - feats.mean()) / feats.std(ddof=1)
    return PreparedData(profiles, feats, z, industry, ratios, notes)


# ==========================================
# 1. PCA: grouping the ratios
# ==========================================
def varimax(loadings: np.ndarray, max_iter: int = 500, tol: float = 1e-8) -> np.ndarray:
    """Varimax rotation with Kaiser normalisation (the jamovi/SPSS default)."""
    p, k = loadings.shape
    if k < 2:
        return loadings
    h = np.sqrt((loadings**2).sum(axis=1, keepdims=True))
    a = loadings / np.where(h == 0, 1, h)
    rot = np.eye(k)
    d_old = 0.0
    for _ in range(max_iter):
        lam = a @ rot
        u, s, vt = np.linalg.svd(a.T @ (lam**3 - lam @ np.diag((lam**2).sum(axis=0)) / p))
        rot = u @ vt
        d = s.sum()
        if d_old and d / d_old < 1 + tol:
            break
        d_old = d
    return (a @ rot) * h


@dataclass
class PCAResult:
    eigenvalues: pd.Series  # all components
    explained: pd.DataFrame  # eigenvalue, % variance, cumulative %
    n_components: int
    loadings: pd.DataFrame  # ratio × component (varimax-rotated)
    scores: pd.DataFrame  # company × component (standardised)
    assignment: pd.DataFrame  # each ratio's main component, loading, textbook category
    names: dict[str, str]  # component → short description


def run_pca(prep: PreparedData, n_components: int | None = None) -> PCAResult:
    z = prep.z
    corr = np.corrcoef(z.values, rowvar=False)
    eigval, eigvec = np.linalg.eigh(corr)
    order = np.argsort(eigval)[::-1]
    eigval, eigvec = eigval[order], eigvec[:, order]
    labels = [f"PC{i + 1}" for i in range(len(eigval))]
    eigenvalues = pd.Series(eigval, index=labels, name="Eigenvalue")
    pct = 100 * eigval / eigval.sum()
    explained = pd.DataFrame({"Eigenvalue": eigval, "% of variance": pct, "Cumulative %": pct.cumsum()}, index=labels)

    k = n_components or max(int((eigval > 1).sum()), 2)  # Kaiser rule: eigenvalue > 1
    raw = eigvec[:, :k] * np.sqrt(eigval[:k])
    rot = varimax(raw)
    # Order rotated components by variance explained; make the largest loading positive
    order = np.argsort((rot**2).sum(axis=0))[::-1]
    rot = rot[:, order]
    rot *= np.where(np.abs(rot.max(axis=0)) >= np.abs(rot.min(axis=0)), 1, -1)
    comp = labels[:k]
    loadings = pd.DataFrame(rot, index=prep.ratios, columns=comp)

    # Regression-method component scores, standardised
    weights = np.linalg.solve(corr, rot)
    scores = pd.DataFrame(z.values @ weights, index=z.index, columns=comp)
    scores = (scores - scores.mean()) / scores.std(ddof=1)

    main = loadings.abs().idxmax(axis=1)
    assignment = pd.DataFrame(
        {
            "Component": main,
            "Loading": [loadings.at[r, c] for r, c in main.items()],
            "Textbook category": [RATIO_SPECS[r].category for r in loadings.index],
        }
    )
    assignment["Communality"] = (loadings**2).sum(axis=1)
    assignment = assignment.sort_values(["Component", "Loading"], key=lambda s: s.abs() if s.name == "Loading" else s,
                                        ascending=[True, False])
    names = {}
    for c in comp:
        top = loadings[c].abs().sort_values(ascending=False).index[:3]
        names[c] = ", ".join(f"{t}{'' if loadings.at[t, c] > 0 else ' (−)'}" for t in top)
    return PCAResult(eigenvalues, explained, k, loadings, scores, assignment, names)


def component_labels(pca: PCAResult) -> dict[str, str]:
    """Short name per component: the textbook category of its strongest
    ratio, with that ratio added when two components share a category."""
    top = {c: pca.loadings[c].abs().idxmax() for c in pca.loadings.columns}
    cats = {c: RATIO_SPECS[r].category for c, r in top.items()}
    counts = pd.Series(cats).value_counts()
    return {c: cats[c] if counts[cats[c]] == 1 else f"{cats[c]} ({top[c]})" for c in top}


# ==========================================
# 2. Cluster analysis: grouping the companies
# ==========================================
@dataclass
class ClusterResult:
    k: int
    labels: pd.Series  # company → cluster number (1..k)
    silhouette: pd.Series  # k → average silhouette (k = 2..8)
    crosstab: pd.DataFrame  # cluster × industry counts
    ari_industry: float  # agreement between clusters and industries (0 = chance, 1 = identical)
    ari_ward: float  # agreement between k-means and Ward hierarchical clustering (stability check)
    profile_z: pd.DataFrame  # cluster × ratio, mean standardised value
    profile_median: pd.DataFrame  # cluster × ratio, median in ratio units
    descriptions: dict[int, str]


def silhouette_by_k(scores: pd.DataFrame, k_range=range(2, 9)) -> pd.Series:
    out = {}
    for k in k_range:
        if k >= len(scores):
            break
        labels = KMeans(k, n_init=50, random_state=RANDOM_STATE).fit_predict(scores)
        out[k] = silhouette_score(scores, labels)
    return pd.Series(out, name="Average silhouette")


def cluster_companies(prep: PreparedData, pca: PCAResult, k: int) -> ClusterResult:
    scores = pca.scores
    km = KMeans(k, n_init=50, random_state=RANDOM_STATE).fit(scores)
    # Number clusters by size (1 = largest) so labels are stable between runs
    sizes = pd.Series(km.labels_).value_counts()
    relabel = {old: new + 1 for new, old in enumerate(sizes.index)}
    labels = pd.Series([relabel[l] for l in km.labels_], index=scores.index, name="Cluster")
    ward = AgglomerativeClustering(n_clusters=k, linkage="ward").fit_predict(scores)

    crosstab = pd.crosstab(labels, prep.industry.reindex(labels.index)).rename_axis(index="Cluster", columns=None)
    profile_z = prep.z.groupby(labels).mean()
    profile_median = prep.profiles[prep.ratios].groupby(labels).median()
    descriptions = {}
    for c in profile_z.index:
        row = profile_z.loc[c].sort_values()
        high = [f"high {r}" for r in row.index[::-1][:3] if row[r] > 0.3]
        low = [f"low {r}" for r in row.index[:2] if row[r] < -0.3]
        descriptions[c] = "; ".join(high + low) or "close to average on all ratios"
    return ClusterResult(
        k=k,
        labels=labels,
        silhouette=silhouette_by_k(scores),
        crosstab=crosstab,
        ari_industry=adjusted_rand_score(prep.industry.reindex(labels.index), labels),
        ari_ward=adjusted_rand_score(labels, ward),
        profile_z=profile_z,
        profile_median=profile_median,
        descriptions=descriptions,
    )


# ==========================================
# 3. Which ratios separate the industries?
# ==========================================
def industry_separation(prep: PreparedData) -> pd.DataFrame:
    """Kruskal–Wallis test per ratio across industries (on company profiles).
    Effect size eta² = (H − k + 1) / (n − k): share of variation explained by industry."""
    rows = []
    groups = prep.industry
    k = groups.nunique()
    for r in prep.ratios:
        vals = prep.profiles[r]
        samples = [vals[groups == g].dropna() for g in groups.unique()]
        samples = [s for s in samples if len(s)]
        if len(samples) < 2:
            continue
        h, p = kruskal(*samples)
        n = sum(len(s) for s in samples)
        medians = {g: vals[groups == g].median() for g in groups.unique()}
        rows.append(
            {
                "Ratio": r,
                "H": h,
                "p-value": p,
                "eta²": max((h - k + 1) / (n - k), 0.0),
                "Highest industry": max(medians, key=lambda g: medians[g]),
                "Lowest industry": min(medians, key=lambda g: medians[g]),
            }
        )
    return pd.DataFrame(rows).sort_values("eta²", ascending=False).reset_index(drop=True)
