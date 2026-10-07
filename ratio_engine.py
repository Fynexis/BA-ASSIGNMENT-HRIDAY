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
INDUSTRY_PROFILES: dict[str, dict[str, tuple[float, float]]] = {
    "Technology / Software": {
        "Gross Profit Margin": (65.0, 85.0),
        "Operating Profit Margin": (18.0, 35.0),
        "Net Profit Margin": (15.0, 30.0),
        "Return on Equity (ROE)": (18.0, 40.0),
        "Current Ratio": (1.8, 4.0),
        "Inventory Turnover": (15.0, 40.0),
        "Days Inventory Outstanding (DIO)": (9.0, 25.0),
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
        "Days Inventory Outstanding (DIO)": (26.0, 60.0),
        "Quick Ratio": (0.2, 0.9),
        "Receivables Turnover": (20.0, 60.0),
        "Days Sales Outstanding (DSO)": (5.0, 18.0),
        "Asset Turnover": (1.5, 3.0),
        "Price-to-Sales (P/S)": (0.3, 1.5),
    },
    "Heavy Manufacturing": {
        "Gross Profit Margin": (18.0, 35.0),
        "Operating Profit Margin": (7.0, 16.0),
        "Asset Turnover": (0.5, 1.1),
        "Inventory Turnover": (3.0, 6.0),
        "Days Inventory Outstanding (DIO)": (60.0, 120.0),
        "Debt-to-Equity": (0.8, 2.2),
        "Debt-to-Assets": (0.35, 0.65),
        "Interest Coverage Ratio": (2.5, 9.0),
        "EV/EBITDA": (6.0, 11.0),
    },
    "Banking / Finance": {
        "Return on Assets (ROA)": (0.5, 1.6),
        "Return on Equity (ROE)": (7.0, 16.0),
        "Equity Multiplier": (8.0, 15.0),
        "Debt-to-Equity": (6.0, 12.0),
        "Debt-to-Assets": (0.85, 0.93),
        "Cash Ratio": (0.05, 0.25),
        "Dividend Yield": (2.5, 6.0),
        "Price-to-Book (P/B)": (0.7, 1.8),
        "Price-to-Earnings (P/E)": (8.0, 15.0),
        "Asset Turnover": (0.04, 0.10),
        "Inventory Turnover": (0.0, 0.0),  # banks hold no inventory
        "Days Inventory Outstanding (DIO)": (0.0, 0.0),
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


def _simulate_series(rng: np.random.Generator, low: float, high: float, n_years: int) -> list[float]:
    """10-year path: a company-specific base level plus a drifting random walk.

    Values are kept within a band around the industry range so trends look
    plausible rather than jumping between unrelated levels each year.
    """
    if high <= 0:
        return [0.0] * n_years
    base = rng.uniform(low, high)
    drift = rng.normal(0.0, 0.02)  # company-specific annual trend
    level = base
    values = []
    for _ in range(n_years):
        level *= 1.0 + drift + rng.normal(0.0, 0.04)
        level = float(np.clip(level, low * 0.6, high * 1.4))
        values.append(round(level, 2))
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
        data_pool[industry] = {}
        for c_idx in range(1, companies_per_industry + 1):
            company_name = f"{INDUSTRY_PREFIX[industry]} Corp {c_idx:02d}"
            matrix = [_simulate_series(rng, *ratio_range(industry, r), len(years)) for r in UNIVERSAL_RATIOS]
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
# 5. FORMATTING & MATRIX STYLING
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
