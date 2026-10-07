"""Core engine for the Cluster & Ratio Analysis Dashboard.

Holds everything that is not UI: the 25 universal ratio definitions, the
industry highlight map, the driver reasoning text, the simulated 10-year
dataset for 100 companies, and the styling/formatting helpers used by the
matrix. Kept free of Streamlit so it can be tested on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

# ==========================================
# 1. UNIVERSAL 25 RATIOS & CATEGORIES
# ==========================================


@dataclass(frozen=True)
class RatioSpec:
    category: str
    unit: str  # "x" (multiple), "%" (percentage) or "days"
    low: float  # typical cross-industry range used for simulation
    high: float
    higher_is_better: bool = True


RATIO_SPECS: dict[str, RatioSpec] = {
    # Liquidity
    "Current Ratio": RatioSpec("Liquidity", "x", 0.8, 3.0),
    "Quick Ratio": RatioSpec("Liquidity", "x", 0.5, 2.5),
    "Cash Ratio": RatioSpec("Liquidity", "x", 0.1, 1.5),
    "Operating Cash Flow Ratio": RatioSpec("Liquidity", "x", 0.2, 1.8),
    "Working Capital Ratio": RatioSpec("Liquidity", "x", 0.8, 2.8),
    # Profitability
    "Gross Profit Margin": RatioSpec("Profitability", "%", 20.0, 60.0),
    "Operating Profit Margin": RatioSpec("Profitability", "%", 5.0, 25.0),
    "Net Profit Margin": RatioSpec("Profitability", "%", 2.0, 18.0),
    "Return on Assets (ROA)": RatioSpec("Profitability", "%", 2.0, 12.0),
    "Return on Equity (ROE)": RatioSpec("Profitability", "%", 6.0, 25.0),
    # Efficiency
    "Asset Turnover": RatioSpec("Efficiency", "x", 0.4, 1.8),
    "Inventory Turnover": RatioSpec("Efficiency", "x", 3.0, 10.0),
    "Receivables Turnover": RatioSpec("Efficiency", "x", 4.0, 12.0),
    "Days Sales Outstanding (DSO)": RatioSpec("Efficiency", "days", 30.0, 90.0, higher_is_better=False),
    "Days Inventory Outstanding (DIO)": RatioSpec("Efficiency", "days", 35.0, 120.0, higher_is_better=False),
    # Leverage
    "Debt-to-Equity": RatioSpec("Leverage", "x", 0.3, 2.0, higher_is_better=False),
    "Debt-to-Assets": RatioSpec("Leverage", "x", 0.2, 0.65, higher_is_better=False),
    "Interest Coverage Ratio": RatioSpec("Leverage", "x", 2.0, 15.0),
    "Equity Multiplier": RatioSpec("Leverage", "x", 1.4, 3.5, higher_is_better=False),
    "Debt Service Coverage Ratio (DSCR)": RatioSpec("Leverage", "x", 1.1, 3.0),
    # Valuation (lower multiples = cheaper, treated as "better" for colouring)
    "Price-to-Earnings (P/E)": RatioSpec("Valuation", "x", 10.0, 30.0, higher_is_better=False),
    "Price-to-Sales (P/S)": RatioSpec("Valuation", "x", 0.5, 4.0, higher_is_better=False),
    "Price-to-Book (P/B)": RatioSpec("Valuation", "x", 1.0, 5.0, higher_is_better=False),
    "EV/EBITDA": RatioSpec("Valuation", "x", 6.0, 18.0, higher_is_better=False),
    "Dividend Yield": RatioSpec("Valuation", "%", 0.5, 4.0),
}

RATIO_CATEGORIES: dict[str, list[str]] = {}
for _name, _spec in RATIO_SPECS.items():
    RATIO_CATEGORIES.setdefault(_spec.category, []).append(_name)

UNIVERSAL_RATIOS: list[str] = list(RATIO_SPECS)

# ==========================================
# 2. INDUSTRY-SPECIFIC HIGHLIGHT MAP
# ==========================================
INDUSTRY_HIGHLIGHTS: dict[str, list[str]] = {
    "Technology / Software": ["Net Profit Margin", "Return on Equity (ROE)", "Current Ratio", "Price-to-Sales (P/S)"],
    "Retail / E-Commerce": ["Gross Profit Margin", "Inventory Turnover", "Quick Ratio", "Receivables Turnover"],
    "Heavy Manufacturing": ["Operating Profit Margin", "Asset Turnover", "Debt-to-Equity", "Interest Coverage Ratio"],
    "Banking / Finance": ["Return on Assets (ROA)", "Equity Multiplier", "Cash Ratio", "Dividend Yield"],
}

INDUSTRY_PREFIX: dict[str, str] = {
    "Technology / Software": "Tech",
    "Retail / E-Commerce": "Retail",
    "Heavy Manufacturing": "Mfg",
    "Banking / Finance": "Bank",
}

# Industry-specific simulation ranges that override the generic RatioSpec
# range, so each cluster carries its characteristic financial fingerprint.
# Ratios in DERIVED_RATIOS are computed from others, so they have no range here.
INDUSTRY_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "Technology / Software": {
        "Gross Profit Margin": (65.0, 85.0),
        "Operating Profit Margin": (18.0, 35.0),
        "Net Profit Margin": (15.0, 30.0),
        "Return on Assets (ROA)": (10.0, 22.0),
        "Current Ratio": (1.8, 4.0),
        "Inventory Turnover": (15.0, 40.0),
        "Debt-to-Equity": (0.1, 0.8),
        "Price-to-Sales (P/S)": (4.0, 15.0),
        "Price-to-Earnings (P/E)": (22.0, 50.0),
        "Dividend Yield": (0.0, 1.2),
    },
    "Retail / E-Commerce": {
        "Gross Profit Margin": (22.0, 45.0),
        "Operating Profit Margin": (2.0, 9.0),
        "Net Profit Margin": (1.0, 6.0),
        "Inventory Turnover": (6.0, 14.0),
        "Quick Ratio": (0.2, 0.9),
        "Receivables Turnover": (20.0, 60.0),
        "Asset Turnover": (1.5, 3.0),
        "Price-to-Sales (P/S)": (0.3, 1.5),
    },
    "Heavy Manufacturing": {
        "Gross Profit Margin": (18.0, 35.0),
        "Operating Profit Margin": (7.0, 16.0),
        "Asset Turnover": (0.5, 1.1),
        "Inventory Turnover": (3.0, 6.0),
        "Debt-to-Equity": (0.8, 2.2),
        "Interest Coverage Ratio": (2.5, 9.0),
        "EV/EBITDA": (6.0, 11.0),
    },
    "Banking / Finance": {
        "Return on Assets (ROA)": (0.5, 1.6),
        "Debt-to-Equity": (7.0, 14.0),
        "Cash Ratio": (0.05, 0.25),
        "Dividend Yield": (2.5, 6.0),
        "Price-to-Book (P/B)": (0.7, 1.8),
        "Price-to-Earnings (P/E)": (8.0, 15.0),
        "Asset Turnover": (0.04, 0.10),
        "Inventory Turnover": (0.0, 0.0),  # banks hold no inventory
    },
}

# ==========================================
# 3. DYNAMIC DRIVER REASONING ENGINE
# ==========================================
INSIGHTS_ENGINE: dict[str, dict[str, str]] = {
    "Technology / Software": {
        "title": "TECH CLUSTER DRIVERS (Asset-Light / IP Model)",
        "Net Profit Margin": "High pricing power driven by near-zero marginal software duplication cost.",
        "Return on Equity (ROE)": "Evaluates efficiency of structural scaling out of intellectual property rather than factory capital.",
        "Current Ratio": "High liquidity requirement to protect massive, high-risk continuous R&D runways.",
        "Price-to-Sales (P/S)": "Crucial anchor ratio used by analysts because rapid topline growth often masks early-stage net earnings.",
    },
    "Retail / E-Commerce": {
        "title": "RETAIL CLUSTER DRIVERS (Low-Margin / High-Velocity)",
        "Gross Profit Margin": "Tracks supplier bargaining power directly against aggressive seasonal markdowns.",
        "Inventory Turnover": "The vital life-support pulse; measures cash velocity trapped on warehouse shelves.",
        "Quick Ratio": "Strips away inventory to verify if raw cash can pay suppliers during quick market corrections.",
        "Receivables Turnover": "Monitors speed of payment clearings from major digital merchant gateways and wholesale links.",
    },
    "Heavy Manufacturing": {
        "title": "MANUFACTURING CLUSTER DRIVERS (Capital-Intense / Structural Fixed Asset)",
        "Operating Profit Margin": "Tracks literal factory-floor output efficiency before considering corporate debt loads.",
        "Asset Turnover": "Validates whether huge multi-year machinery (PP&E) capital assets generate real revenue velocity.",
        "Debt-to-Equity": "Assembly line infrastructure requires immense long-term debt; this maps fundamental solvency boundaries.",
        "Interest Coverage Ratio": "Measures if operating income securely dwarfs the persistent weight of recurring loan interest.",
    },
    "Banking / Finance": {
        "title": "BANKING CLUSTER DRIVERS (Highly-Leveraged Reserve Model)",
        "Return on Assets (ROA)": "Since loan portfolios are the assets, minor ticks show tectonic shifts in credit underwriting quality.",
        "Equity Multiplier": "Banks purposefully leverage capital base 10x-15x; this maps systemic scale risk.",
        "Cash Ratio": "Strict control verification metric to track mandatory central bank liquidity reserve compliance.",
        "Dividend Yield": "Capital clusters are traditionally mature frameworks satisfying long-term yield institutional fund mandates.",
    },
}


def build_insight_markdown(
    industry: str,
    company_df: pd.DataFrame | None = None,
    year: str | None = None,
    peer_medians: pd.Series | None = None,
) -> str:
    """Compose the driver rationale for an industry.

    When a company snapshot, anchor year and peer medians are given, each
    driver line also states the company's value and whether it beats the
    cluster median, so the reasoning reacts to the current selection.
    """
    insight = INSIGHTS_ENGINE[industry]
    lines = [f"💡 **{insight['title']}**", ""]
    for ratio in INDUSTRY_HIGHLIGHTS[industry]:
        line = f"* **{ratio}**: {insight[ratio]}"
        if company_df is not None and year is not None and peer_medians is not None:
            value = float(company_df.at[ratio, year])
            median = float(peer_medians[ratio])
            verdict = "ahead of" if is_favourable(ratio, value, median) else "behind"
            line += (
                f"  \n  ↳ {year}: **{format_value(ratio, value)}** vs cluster median "
                f"{format_value(ratio, median)} — {verdict} peers."
            )
        lines.append(line)
    return "\n".join(lines)


# ==========================================
# 4. DATA ENGINE (10 YEARS × 100 COMPANIES)
# ==========================================
YEARS: list[str] = [str(y) for y in range(2017, 2027)]
COMPANIES_PER_INDUSTRY = 25
DEFAULT_SEED = 42


def ratio_range(industry: str, ratio: str) -> tuple[float, float]:
    spec = RATIO_SPECS[ratio]
    return INDUSTRY_PROFILES.get(industry, {}).get(ratio, (spec.low, spec.high))


# Latent drivers behind every ratio. Each company has a level on each factor,
# the whole industry drifts together year to year (macro cycle), and each
# company deviates around that. Ratios load on the factors, which is what
# makes them correlate the way real statements do (e.g. more leverage ->
# weaker interest coverage).
FACTORS = ["Profitability", "Leverage", "Liquidity", "Efficiency", "Market Sentiment"]

FACTOR_LOADINGS: dict[str, dict[str, float]] = {
    "Current Ratio": {"Liquidity": 1.0, "Leverage": -0.4},
    "Quick Ratio": {"Liquidity": 1.0, "Leverage": -0.3},
    "Cash Ratio": {"Liquidity": 0.9, "Leverage": -0.3, "Profitability": 0.2},
    "Operating Cash Flow Ratio": {"Liquidity": 0.5, "Profitability": 0.6, "Efficiency": 0.3},
    "Working Capital Ratio": {"Liquidity": 1.0},
    "Gross Profit Margin": {"Profitability": 0.9},
    "Operating Profit Margin": {"Profitability": 1.0, "Efficiency": 0.2},
    "Net Profit Margin": {"Profitability": 1.0, "Leverage": -0.2},
    "Return on Assets (ROA)": {"Profitability": 0.8, "Efficiency": 0.5},
    "Asset Turnover": {"Efficiency": 1.0},
    "Inventory Turnover": {"Efficiency": 0.9},
    "Receivables Turnover": {"Efficiency": 0.8},
    "Debt-to-Equity": {"Leverage": 1.0},
    "Interest Coverage Ratio": {"Profitability": 0.7, "Leverage": -0.7},
    "Debt Service Coverage Ratio (DSCR)": {"Profitability": 0.6, "Leverage": -0.6, "Liquidity": 0.2},
    "Price-to-Earnings (P/E)": {"Market Sentiment": 1.0},
    "Price-to-Sales (P/S)": {"Market Sentiment": 0.8, "Profitability": 0.6},
    "Price-to-Book (P/B)": {"Market Sentiment": 0.7, "Profitability": 0.6},
    "EV/EBITDA": {"Market Sentiment": 0.9, "Profitability": 0.2},
    "Dividend Yield": {"Market Sentiment": -0.8, "Profitability": 0.3},
}

# Ratios computed from others through accounting identities, in dependency order.
DERIVED_RATIOS: dict[str, str] = {
    "Equity Multiplier": "1 + Debt-to-Equity",
    "Debt-to-Assets": "Debt-to-Equity / (1 + Debt-to-Equity)",
    "Return on Equity (ROE)": "ROA × Equity Multiplier (DuPont)",
    "Days Sales Outstanding (DSO)": "365 / Receivables Turnover",
    "Days Inventory Outstanding (DIO)": "365 / Inventory Turnover",
}

# Pairs linked by definition, so a strong correlation between them is expected
# rather than an economic finding.
IDENTITY_PAIRS: set[frozenset[str]] = {
    frozenset(p)
    for p in [
        ("Debt-to-Equity", "Equity Multiplier"),
        ("Debt-to-Equity", "Debt-to-Assets"),
        ("Equity Multiplier", "Debt-to-Assets"),
        ("Return on Assets (ROA)", "Return on Equity (ROE)"),
        ("Equity Multiplier", "Return on Equity (ROE)"),
        ("Receivables Turnover", "Days Sales Outstanding (DSO)"),
        ("Inventory Turnover", "Days Inventory Outstanding (DIO)"),
    ]
}

IDIOSYNCRATIC_SD = 0.5  # company-specific, persistent part of each ratio
YEARLY_NOISE_SD = 0.15  # one-off year-to-year noise


def _simulate_industry(rng: np.random.Generator, industry: str, n_companies: int, n_years: int) -> dict[str, np.ndarray]:
    """Return ``{ratio: array[company, year]}`` for one industry."""
    n_factors = len(FACTORS)
    company_level = rng.normal(0.0, 1.0, (n_companies, n_factors))
    # Industry-wide cycle shared by all companies (random walk).
    macro = np.cumsum(rng.normal(0.0, 0.15, (n_years, n_factors)), axis=0)
    # Company-specific deviations that persist for a few years (AR(1)).
    deviation = np.zeros((n_companies, n_years, n_factors))
    deviation[:, 0] = rng.normal(0.0, 0.3, (n_companies, n_factors))
    for t in range(1, n_years):
        deviation[:, t] = 0.6 * deviation[:, t - 1] + rng.normal(0.0, 0.3, (n_companies, n_factors))
    factors = company_level[:, None, :] + macro[None, :, :] + deviation

    values: dict[str, np.ndarray] = {}
    for ratio, loadings in FACTOR_LOADINGS.items():
        weights = np.array([loadings.get(f, 0.0) for f in FACTORS])
        idio = rng.normal(0.0, IDIOSYNCRATIC_SD, (n_companies, 1))
        noise = rng.normal(0.0, YEARLY_NOISE_SD, (n_companies, n_years))
        norm = np.sqrt((weights**2).sum() + IDIOSYNCRATIC_SD**2 + YEARLY_NOISE_SD**2)
        z = (factors @ weights + idio + noise) / norm
        position = 1.0 / (1.0 + np.exp(-1.7 * z))  # squash into (0, 1)
        low, high = ratio_range(industry, ratio)
        values[ratio] = low + (high - low) * position

    de = values["Debt-to-Equity"]
    values["Equity Multiplier"] = 1.0 + de
    values["Debt-to-Assets"] = de / (1.0 + de)
    values["Return on Equity (ROE)"] = values["Return on Assets (ROA)"] * values["Equity Multiplier"]
    values["Days Sales Outstanding (DSO)"] = 365.0 / values["Receivables Turnover"]
    inv = values["Inventory Turnover"]
    values["Days Inventory Outstanding (DIO)"] = np.divide(365.0, inv, out=np.zeros_like(inv), where=inv > 0)
    return values


def generate_dataset(
    seed: int = DEFAULT_SEED,
    companies_per_industry: int = COMPANIES_PER_INDUSTRY,
    years: list[str] = YEARS,
) -> dict[str, dict[str, pd.DataFrame]]:
    """Return ``{industry: {company: DataFrame}}``.

    Each DataFrame is indexed by the 25 universal ratios, with a
    ``Ratio Category`` column followed by one column per year.
    """
    rng = np.random.default_rng(seed)
    categories = [RATIO_SPECS[r].category for r in UNIVERSAL_RATIOS]
    data_pool: dict[str, dict[str, pd.DataFrame]] = {}

    for industry in INDUSTRY_HIGHLIGHTS:
        values = _simulate_industry(rng, industry, companies_per_industry, len(years))
        data_pool[industry] = {}
        for c_idx in range(companies_per_industry):
            company_name = f"{INDUSTRY_PREFIX[industry]} Corp {c_idx + 1:02d}"
            matrix = np.array([values[r][c_idx] for r in UNIVERSAL_RATIOS]).round(2)
            df = pd.DataFrame(matrix, index=UNIVERSAL_RATIOS, columns=years)
            df.index.name = "Ratio"
            df.insert(0, "Ratio Category", categories)
            data_pool[industry][company_name] = df

    return data_pool


def peer_snapshot(data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, year: str) -> pd.DataFrame:
    """Ratios (rows) × companies (columns) for one industry in one year."""
    return pd.DataFrame({name: df[year] for name, df in data_pool[industry].items()})


def is_favourable(ratio: str, value: float, benchmark: float) -> bool:
    if RATIO_SPECS[ratio].higher_is_better:
        return value >= benchmark
    return value <= benchmark


def peer_percentile(ratio: str, value: float, peer_values: pd.Series) -> float:
    """Share of peers (0-100) the company is at least as good as."""
    if RATIO_SPECS[ratio].higher_is_better:
        beaten = (peer_values <= value).sum()
    else:
        beaten = (peer_values >= value).sum()
    return round(100.0 * beaten / len(peer_values), 1)


# ==========================================
# 5. CORRELATION & INDUSTRY ANALYTICS
# ==========================================
def industry_panel(
    data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, year: str | None = None
) -> pd.DataFrame:
    """One row per (company, year) observation, one column per ratio.

    With ``year`` set, only that year's cross-section of companies is kept.
    """
    frames = []
    for company, df in data_pool[industry].items():
        cols = [year] if year is not None else [c for c in df.columns if c != "Ratio Category"]
        block = df[cols].T
        block.index = pd.MultiIndex.from_product([[company], cols], names=["Company", "Year"])
        frames.append(block)
    panel = pd.concat(frames)
    panel.columns.name = None
    return panel[UNIVERSAL_RATIOS]


def correlation_matrix(panel: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """25 × 25 correlation matrix. Ratios with no variation (e.g. a bank's
    inventory turnover) come out as NaN because correlation is undefined."""
    return panel.corr(method=method)


def correlation_strength(r: float) -> str:
    a = abs(r)
    if a >= 0.7:
        return "Strong"
    if a >= 0.4:
        return "Moderate"
    if a >= 0.2:
        return "Weak"
    return "Negligible"


def describe_correlation(ratio_a: str, ratio_b: str, r: float) -> str:
    """Plain-language reading of a correlation coefficient."""
    if np.isnan(r):
        return "Correlation cannot be measured: one of the ratios does not vary in this sample."
    strength = correlation_strength(r)
    if strength == "Negligible":
        return f"**{ratio_a}** and **{ratio_b}** move largely independently (r = {r:+.2f})."
    if r > 0:
        return (
            f"When **{ratio_a}** goes up, **{ratio_b}** tends to go **up** too "
            f"({strength.lower()} positive correlation, r = {r:+.2f})."
        )
    return (
        f"When **{ratio_a}** goes up, **{ratio_b}** tends to go **down** "
        f"({strength.lower()} negative correlation, r = {r:+.2f})."
    )


def top_correlations(corr: pd.DataFrame, include_identities: bool = True) -> pd.DataFrame:
    """Every distinct ratio pair, sorted from strongest to weakest |r|."""
    rows = []
    names = list(corr.index)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            r = corr.at[a, b]
            if np.isnan(r):
                continue
            identity = frozenset((a, b)) in IDENTITY_PAIRS
            if identity and not include_identities:
                continue
            rows.append(
                {
                    "Ratio A": a,
                    "Ratio B": b,
                    "r": round(float(r), 3),
                    "Direction": "Move together ↑↑" if r > 0 else "Move opposite ↑↓",
                    "Strength": correlation_strength(r),
                    "Link": "Accounting identity" if identity else "Economic",
                }
            )
    out = pd.DataFrame(rows, columns=["Ratio A", "Ratio B", "r", "Direction", "Strength", "Link"])
    return out.reindex(out["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def regression_slope(x: pd.Series, y: pd.Series) -> float:
    """Least-squares slope: change in y for a one-unit increase in x."""
    if x.nunique() < 2:
        return float("nan")
    return float(np.polyfit(x.astype(float), y.astype(float), 1)[0])


def industry_category_summary(
    data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, category: str, year: str
) -> pd.DataFrame:
    """Distribution of each ratio in a category across the industry's companies."""
    snap = peer_snapshot(data_pool, industry, year).loc[RATIO_CATEGORIES[category]]
    rows = []
    for ratio, values in snap.iterrows():
        best = values.idxmax() if RATIO_SPECS[ratio].higher_is_better else values.idxmin()
        rows.append(
            {
                "Ratio": ratio,
                "Median": values.median(),
                "Mean": values.mean(),
                "P25": values.quantile(0.25),
                "P75": values.quantile(0.75),
                "Min": values.min(),
                "Max": values.max(),
                "Best Company": best if values.nunique() > 1 else "—",
            }
        )
    return pd.DataFrame(rows).set_index("Ratio")


def industry_trend(data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, ratio: str) -> pd.DataFrame:
    """Industry P25 / median / P75 for one ratio, by year."""
    rows = {}
    for year in YEARS:
        values = peer_snapshot(data_pool, industry, year).loc[ratio]
        rows[year] = {"P25": values.quantile(0.25), "Median": values.median(), "P75": values.quantile(0.75)}
    return pd.DataFrame(rows).T.rename_axis("Year")


def cross_industry_medians(data_pool: dict[str, dict[str, pd.DataFrame]], category: str, year: str) -> pd.DataFrame:
    """Median of each ratio in a category, one column per industry."""
    return pd.DataFrame(
        {ind: peer_snapshot(data_pool, ind, year).loc[RATIO_CATEGORIES[category]].median(axis=1) for ind in data_pool}
    )


def category_scores(
    data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, category: str, year: str
) -> pd.Series:
    """Composite 0-100 score per company: its average peer percentile across
    the category's ratios (direction-aware). Ratios with no variation are skipped."""
    snap = peer_snapshot(data_pool, industry, year).loc[RATIO_CATEGORIES[category]]
    snap = snap[snap.nunique(axis=1) > 1]
    scores = {
        company: np.mean([peer_percentile(r, snap.at[r, company], snap.loc[r]) for r in snap.index])
        for company in snap.columns
    }
    return pd.Series(scores, name=f"{category} Score").sort_values(ascending=False).round(1)


# ==========================================
# 6. FORMATTING & MATRIX STYLING
# ==========================================
def format_value(ratio: str, value: float) -> str:
    unit = RATIO_SPECS[ratio].unit
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "days":
        return f"{value:.1f}d"
    return f"{value:.2f}x"


HIGHLIGHT_STYLE = "background-color: #1e4620; color: #ffffff; font-weight: bold;"
HIGHLIGHT_ANCHOR_STYLE = "background-color: #2e7d32; color: #ffffff; font-weight: bold;"
NEUTRAL_STYLE = "color: #888888;"
NEUTRAL_ANCHOR_STYLE = "background-color: rgba(128, 128, 128, 0.15); color: #888888;"


def matrix_styles(df: pd.DataFrame, highlights: list[str], anchor_year: str | None = None) -> pd.DataFrame:
    """CSS for every cell: the industry drivers light up in emerald, the other
    rows fade to neutral grey, and the anchor-year column is tinted.

    Rows are identified by the ``Ratio`` column when present, else the index.
    """
    ratios = df["Ratio"] if "Ratio" in df.columns else pd.Series(df.index, index=df.index)
    styles = pd.DataFrame("", index=df.index, columns=df.columns)
    for row, ratio in ratios.items():
        is_highlight = ratio in highlights
        styles.loc[row, :] = HIGHLIGHT_STYLE if is_highlight else NEUTRAL_STYLE
        if anchor_year is not None and anchor_year in df.columns:
            styles.loc[row, anchor_year] = HIGHLIGHT_ANCHOR_STYLE if is_highlight else NEUTRAL_ANCHOR_STYLE
    return styles


def style_matrix(df: pd.DataFrame, highlights: list[str], anchor_year: str | None = None):
    """Return a pandas Styler with highlighting and unit-aware number formats.

    The ratio names are moved from the index into a ``Ratio`` column so the
    highlight covers the name too; render it with ``hide_index=True``.
    """
    display = df.reset_index()
    year_cols = [c for c in df.columns if c != "Ratio Category"]
    styler = display.style.apply(lambda d: matrix_styles(d, highlights, anchor_year), axis=None)
    for row, ratio in display["Ratio"].items():
        styler = styler.format(
            lambda v, r=ratio: format_value(r, v),
            subset=pd.IndexSlice[[row], year_cols],
        )
    return styler
