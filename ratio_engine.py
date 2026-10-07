"""Core engine for the Cluster & Ratio Analysis Dashboard.

Holds everything that is not UI: the 25 universal ratio definitions, the
industry highlight map, the driver reasoning text, the loader that turns a
company financials workbook into the 25 ratios, the correlation / industry
analytics, and the styling helpers used by the matrix. Kept free of
Streamlit so it can be tested on its own.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

# ==========================================
# 1. UNIVERSAL 25 RATIOS & CATEGORIES
# ==========================================


@dataclass(frozen=True)
class RatioSpec:
    category: str
    unit: str  # "x" (multiple), "%" (percentage) or "days"
    formula: str
    higher_is_better: bool = True


RATIO_SPECS: dict[str, RatioSpec] = {
    # Liquidity
    "Current Ratio": RatioSpec("Liquidity", "x", "Current Assets / Current Liabilities"),
    "Quick Ratio": RatioSpec("Liquidity", "x", "(Current Assets − Inventory) / Current Liabilities"),
    "Cash Ratio": RatioSpec("Liquidity", "x", "Cash & ST Investments / Current Liabilities"),
    "Operating Cash Flow Ratio": RatioSpec("Liquidity", "x", "Cash from Operations / Current Liabilities"),
    "Working Capital Ratio": RatioSpec("Liquidity", "x", "(Current Assets − Current Liabilities) / Total Assets"),
    # Profitability
    "Gross Profit Margin": RatioSpec("Profitability", "%", "Gross Profit / Revenue × 100"),
    "Operating Profit Margin": RatioSpec("Profitability", "%", "EBIT / Revenue × 100"),
    "Net Profit Margin": RatioSpec("Profitability", "%", "Net Income / Revenue × 100"),
    "Return on Assets (ROA)": RatioSpec("Profitability", "%", "Net Income / Total Assets × 100"),
    "Return on Equity (ROE)": RatioSpec("Profitability", "%", "Net Income / Total Equity × 100 (equity > 0)"),
    # Efficiency
    "Asset Turnover": RatioSpec("Efficiency", "x", "Revenue / Total Assets"),
    "Inventory Turnover": RatioSpec("Efficiency", "x", "COGS / Inventory (inventory reported)"),
    "Receivables Turnover": RatioSpec("Efficiency", "x", "Revenue / Receivables"),
    "Days Sales Outstanding (DSO)": RatioSpec("Efficiency", "days", "365 / Receivables Turnover", higher_is_better=False),
    "Days Inventory Outstanding (DIO)": RatioSpec("Efficiency", "days", "365 / Inventory Turnover", higher_is_better=False),
    # Leverage
    "Debt-to-Equity": RatioSpec("Leverage", "x", "Total Debt / Total Equity (equity > 0)", higher_is_better=False),
    "Debt-to-Assets": RatioSpec("Leverage", "x", "Total Debt / Total Assets", higher_is_better=False),
    "Interest Coverage Ratio": RatioSpec("Leverage", "x", "EBIT / Interest Expense (interest > 0)"),
    "Equity Multiplier": RatioSpec("Leverage", "x", "Total Assets / Total Equity (equity > 0)", higher_is_better=False),
    "Debt Service Coverage Ratio (DSCR)": RatioSpec("Leverage", "x", "EBITDA / (Interest + Debt Repaid)"),
    # Valuation (lower multiples = cheaper, treated as "better" for colouring)
    "Price-to-Earnings (P/E)": RatioSpec("Valuation", "x", "Market Cap / Net Income (profit > 0)", higher_is_better=False),
    "Price-to-Sales (P/S)": RatioSpec("Valuation", "x", "Market Cap / Revenue", higher_is_better=False),
    "Price-to-Book (P/B)": RatioSpec("Valuation", "x", "Market Cap / Total Equity (equity > 0)", higher_is_better=False),
    "EV/EBITDA": RatioSpec("Valuation", "x", "Enterprise Value / EBITDA (EBITDA > 0)", higher_is_better=False),
    "Dividend Yield": RatioSpec("Valuation", "%", "Dividend per Share / Share Price × 100"),
}

RATIO_CATEGORIES: dict[str, list[str]] = {}
for _name, _spec in RATIO_SPECS.items():
    RATIO_CATEGORIES.setdefault(_spec.category, []).append(_name)

UNIVERSAL_RATIOS: list[str] = list(RATIO_SPECS)

# Pairs linked by how they are calculated, so a strong correlation between
# them is expected rather than an economic finding.
IDENTITY_PAIRS: set[frozenset[str]] = {
    frozenset(p)
    for p in [
        ("Receivables Turnover", "Days Sales Outstanding (DSO)"),
        ("Inventory Turnover", "Days Inventory Outstanding (DIO)"),
        ("Return on Assets (ROA)", "Return on Equity (ROE)"),  # ROE = ROA × Equity Multiplier
        ("Equity Multiplier", "Return on Equity (ROE)"),
        ("Debt-to-Equity", "Equity Multiplier"),  # D/E = D/A × Equity Multiplier
        ("Debt-to-Equity", "Debt-to-Assets"),
        ("Current Ratio", "Quick Ratio"),  # same denominator, overlapping numerator
    ]
}

# ==========================================
# 2. INDUSTRY-SPECIFIC HIGHLIGHT MAP
# ==========================================
INDUSTRY_HIGHLIGHTS: dict[str, list[str]] = {
    "Technology / Software": ["Net Profit Margin", "Return on Equity (ROE)", "Current Ratio", "Price-to-Sales (P/S)"],
    "Pharmaceuticals": ["Gross Profit Margin", "Return on Equity (ROE)", "Days Sales Outstanding (DSO)", "Price-to-Earnings (P/E)"],
    "FMCG": ["Operating Profit Margin", "Inventory Turnover", "Return on Equity (ROE)", "Dividend Yield"],
    "Infrastructure / Heavy Manufacturing": ["Operating Profit Margin", "Asset Turnover", "Debt-to-Equity", "Interest Coverage Ratio"],
}

DEFAULT_HIGHLIGHTS = ["Net Profit Margin", "Return on Equity (ROE)", "Debt-to-Equity", "Asset Turnover"]

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
    "Pharmaceuticals": {
        "title": "PHARMA CLUSTER DRIVERS (R&D / Regulatory Model)",
        "Gross Profit Margin": "Reflects product mix: branded, specialty and complex generics earn far more than commodity generics and APIs, and US price erosion shows up here first.",
        "Return on Equity (ROE)": "R&D pipelines and new-drug filings are funded from shareholders' capital; ROE shows whether that intangible investment pays off.",
        "Days Sales Outstanding (DSO)": "Export-heavy drug makers sell to overseas wholesalers and distributors on long credit terms; rising DSO flags collection risk or channel stuffing.",
        "Price-to-Earnings (P/E)": "The market prices pipeline and regulatory (USFDA inspection) risk into the earnings multiple; de-ratings often follow warning letters.",
    },
    "FMCG": {
        "title": "FMCG CLUSTER DRIVERS (Brand / Distribution Model)",
        "Operating Profit Margin": "Shows brand pricing power against volatile input costs (edible oils, grains, packaging): strong brands pass inflation on and protect margins.",
        "Inventory Turnover": "Fast-moving goods with short shelf lives; turnover measures how efficiently the distribution network clears stock.",
        "Return on Equity (ROE)": "Asset-light, low-working-capital business models let the strongest consumer brands earn exceptionally high returns on equity.",
        "Dividend Yield": "Mature, cash-generative companies with high payout ratios; yield anchors valuation for income-focused investors.",
    },
    "Infrastructure / Heavy Manufacturing": {
        "title": "INFRA & MANUFACTURING CLUSTER DRIVERS (Capital-Intense / Fixed Asset)",
        "Operating Profit Margin": "Tracks factory-floor and project execution efficiency before considering corporate debt loads.",
        "Asset Turnover": "Validates whether large multi-year plant and machinery investments generate real revenue.",
        "Debt-to-Equity": "Plants and projects are funded with long-term debt; this maps fundamental solvency boundaries.",
        "Interest Coverage Ratio": "Measures whether operating income comfortably covers the recurring weight of loan interest.",
    },
}


def highlights_for(industry: str) -> list[str]:
    return INDUSTRY_HIGHLIGHTS.get(industry, DEFAULT_HIGHLIGHTS)


def build_insight_markdown(
    industry: str,
    company_df: pd.DataFrame | None = None,
    year: str | None = None,
    peer_medians: pd.Series | None = None,
) -> str:
    """Compose the driver rationale for an industry.

    When a company snapshot, anchor year and peer medians are given, each
    driver line also states the company's value and whether it beats the
    industry median, so the reasoning reacts to the current selection.
    """
    insight = INSIGHTS_ENGINE.get(industry, {"title": f"{industry.upper()} CLUSTER DRIVERS"})
    lines = [f"💡 **{insight['title']}**", ""]
    for ratio in highlights_for(industry):
        line = f"* **{ratio}**: {insight.get(ratio, RATIO_SPECS[ratio].formula)}"
        if company_df is not None and year is not None and peer_medians is not None:
            value = float(company_df.at[ratio, year])
            median = float(peer_medians[ratio])
            if np.isnan(value) or np.isnan(median):
                line += f"  \n  ↳ {year}: not meaningful for this company (see data notes)."
            else:
                verdict = "ahead of" if is_favourable(ratio, value, median) else "behind"
                line += (
                    f"  \n  ↳ {year}: **{format_value(ratio, value)}** vs industry median "
                    f"{format_value(ratio, median)} — {verdict} peers."
                )
        lines.append(line)
    return "\n".join(lines)


# ==========================================
# 4. DATA LOADER: FINANCIALS → 25 RATIOS
# ==========================================
# Columns expected in the "Data" sheet (same layout as data/capiq_template.xlsx).
ITEM_COLUMNS = [
    "Total Revenue", "Cost of Goods Sold", "Gross Profit", "EBIT", "EBITDA", "Interest Expense", "Net Income",
    "Total Current Assets", "Total Current Liabilities", "Cash & ST Investments", "Inventory", "Total Receivables",
    "Total Assets", "Total Debt", "Total Equity", "Cash from Operations", "Debt Repaid", "Dividend per Share",
    "Share Price (period end)", "Market Cap", "Total Enterprise Value",
]
PLACEHOLDER_NOTE = re.compile(r"set to 0:\s*(?P<items>[^;]+)", re.IGNORECASE)


@dataclass
class FinancialData:
    raw: pd.DataFrame  # one row per company-year, cleaned financial items
    ratios: pd.DataFrame  # one row per company-year, the 25 ratios
    pool: dict[str, dict[str, pd.DataFrame]]  # {industry: {company: ratio matrix}}
    years: list[str]
    issues: list[str] = field(default_factory=list)


def _read_table(source) -> pd.DataFrame:
    """Read the Data sheet of an .xlsx workbook (header on row 2, Capital IQ
    mnemonics on row 3) or a flat .csv with the same column names."""
    name = str(getattr(source, "name", source)).lower()
    if name.endswith(".csv"):
        df = pd.read_csv(source)
    else:
        df = pd.read_excel(source, sheet_name="Data", header=1)
        if len(df) and str(df.iloc[0].get("Total Revenue", "")).startswith("IQ_"):
            df = df.iloc[1:]
    missing = [c for c in ["Industry", "Company", *ITEM_COLUMNS] if c not in df.columns]
    if missing:
        raise ValueError(f"Data is missing columns: {', '.join(missing)}")
    return df.dropna(subset=["Company"]).reset_index(drop=True)


def _fiscal_label(row: pd.Series) -> str:
    period = str(row.get("Period", ""))
    if re.fullmatch(r"FY\d{4}", period):
        return period
    date = pd.to_datetime(row.get("Period End Date"), errors="coerce")
    if pd.isna(date):
        raise ValueError(f"Cannot tell the fiscal year for {row['Company']} ({period})")
    return f"FY{date.year}"


def clean_financials(df: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Numeric items, a FY label per row, and 'not reported, set to 0'
    placeholders turned back into missing values."""
    out = df.copy()
    issues: list[str] = []
    out["Year"] = out.apply(_fiscal_label, axis=1)
    for col in ITEM_COLUMNS:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    notes = out["Notes"] if "Notes" in out.columns else pd.Series("", index=out.index)
    n_placeholders = 0
    for idx, note in notes.fillna("").astype(str).items():
        m = PLACEHOLDER_NOTE.search(note)
        if not m:
            continue
        for item in m.group("items").split(","):
            col = next((c for c in ITEM_COLUMNS if c.lower() == item.strip().lower()), None)
            if col:
                out.at[idx, col] = np.nan
                n_placeholders += 1
    if n_placeholders:
        issues.append(f"{n_placeholders} values marked 'not reported, set to 0' were treated as missing, not zero.")
    dupes = int(out.duplicated(["Company", "Year"]).sum())
    if dupes:
        issues.append(f"{dupes} duplicate company-year rows were dropped.")
        out = out.drop_duplicates(["Company", "Year"])
    return out, issues


def _div(num: pd.Series, den: pd.Series) -> pd.Series:
    """num / den, blank where the denominator is missing, zero or negative,
    since those ratios are not meaningful."""
    den = den.astype(float)
    return (num.astype(float) / den.where(den > 0)).astype(float)


def compute_ratios(fin: pd.DataFrame) -> pd.DataFrame:
    """The 25 ratios for every company-year (formulas in RATIO_SPECS)."""
    f = fin
    r = pd.DataFrame(index=f.index)
    cl = f["Total Current Liabilities"]
    rev = f["Total Revenue"]
    r["Current Ratio"] = _div(f["Total Current Assets"], cl)
    r["Quick Ratio"] = _div(f["Total Current Assets"] - f["Inventory"].fillna(0), cl)
    r["Cash Ratio"] = _div(f["Cash & ST Investments"], cl)
    r["Operating Cash Flow Ratio"] = _div(f["Cash from Operations"], cl)
    r["Working Capital Ratio"] = _div(f["Total Current Assets"] - cl, f["Total Assets"])
    r["Gross Profit Margin"] = 100 * _div(f["Gross Profit"], rev)
    r["Operating Profit Margin"] = 100 * _div(f["EBIT"], rev)
    r["Net Profit Margin"] = 100 * _div(f["Net Income"], rev)
    r["Return on Assets (ROA)"] = 100 * _div(f["Net Income"], f["Total Assets"])
    r["Return on Equity (ROE)"] = 100 * _div(f["Net Income"], f["Total Equity"])
    r["Asset Turnover"] = _div(rev, f["Total Assets"])
    r["Inventory Turnover"] = _div(f["Cost of Goods Sold"], f["Inventory"])
    r["Receivables Turnover"] = _div(rev, f["Total Receivables"])
    days = pd.Series(365.0, index=f.index)
    r["Days Sales Outstanding (DSO)"] = _div(days, r["Receivables Turnover"])
    r["Days Inventory Outstanding (DIO)"] = _div(days, r["Inventory Turnover"])
    r["Debt-to-Equity"] = _div(f["Total Debt"], f["Total Equity"])
    r["Debt-to-Assets"] = _div(f["Total Debt"], f["Total Assets"])
    r["Interest Coverage Ratio"] = _div(f["EBIT"], f["Interest Expense"])
    r["Equity Multiplier"] = _div(f["Total Assets"], f["Total Equity"])
    r["Debt Service Coverage Ratio (DSCR)"] = _div(f["EBITDA"], f["Interest Expense"] + f["Debt Repaid"].fillna(0))
    r["Price-to-Earnings (P/E)"] = _div(f["Market Cap"], f["Net Income"])
    r["Price-to-Sales (P/S)"] = _div(f["Market Cap"], rev)
    r["Price-to-Book (P/B)"] = _div(f["Market Cap"], f["Total Equity"])
    r["EV/EBITDA"] = _div(f["Total Enterprise Value"], f["EBITDA"])
    r["Dividend Yield"] = 100 * _div(f["Dividend per Share"], f["Share Price (period end)"])
    r = r.replace([np.inf, -np.inf], np.nan).round(4)
    return pd.concat([f[["Industry", "Company", "Year"]], r[UNIVERSAL_RATIOS]], axis=1)


def build_pool(ratios: pd.DataFrame, years: list[str]) -> dict[str, dict[str, pd.DataFrame]]:
    categories = [RATIO_SPECS[r].category for r in UNIVERSAL_RATIOS]
    pool: dict[str, dict[str, pd.DataFrame]] = {}
    for (industry, company), grp in ratios.groupby(["Industry", "Company"], sort=False):
        mat = grp.set_index("Year")[UNIVERSAL_RATIOS].T.reindex(columns=years).astype(float)
        mat.index.name = "Ratio"
        mat.insert(0, "Ratio Category", categories)
        pool.setdefault(industry, {})[company] = mat
    return pool


def load_financials(source) -> FinancialData:
    """Load a financials workbook/CSV and derive the 25 ratios."""
    raw, issues = clean_financials(_read_table(source))
    years = sorted(raw["Year"].unique())
    ratios = compute_ratios(raw)
    counts = raw.groupby("Company")["Year"].nunique()
    short = counts[counts < len(years)]
    if len(short):
        issues.append(f"{len(short)} companies have fewer than {len(years)} years: {', '.join(short.index[:10])}.")
    blanks = ratios[UNIVERSAL_RATIOS].isna().sum()
    blanks = blanks[blanks > 0].sort_values(ascending=False)
    if len(blanks):
        top = ", ".join(f"{r} ({n})" for r, n in blanks.head(6).items())
        issues.append(f"Ratios left blank where not meaningful, by number of company-years: {top}.")
    return FinancialData(raw=raw, ratios=ratios, pool=build_pool(ratios, years), years=years, issues=issues)


def data_checks(data: FinancialData) -> pd.DataFrame:
    """Company-years whose numbers look suspicious, with the reason. The
    values are kept as they are; this list is for the user to verify."""
    raw, r = data.raw, data.ratios
    checks = []

    def flag(mask: pd.Series, issue: str, value_col: str | None = None, ratio: str | None = None) -> None:
        for idx in mask[mask.fillna(False)].index:
            value = ""
            if ratio:
                value = format_value(ratio, r.at[idx, ratio])
            elif value_col:
                value = f"{raw.at[idx, value_col]:,.2f}"
            checks.append({"Company": raw.at[idx, "Company"], "Year": raw.at[idx, "Year"], "Value": value, "Issue": issue})

    flag(r["Dividend Yield"] > 10, "Dividend yield above 10%: check the share price and dividend are on the same "
         "split/bonus/demerger-adjusted basis.", ratio="Dividend Yield")
    for m in ["Gross Profit Margin", "Operating Profit Margin", "Net Profit Margin"]:
        flag(r[m] < -100, f"{m} below −100%: revenue is tiny relative to costs.", ratio=m)
    flag(r["Gross Profit Margin"] >= 99.5, "Gross margin of ~100%: cost of goods sold is zero or missing.",
         ratio="Gross Profit Margin")
    flag(r["EV/EBITDA"] > 100, "EBITDA is close to zero, so EV/EBITDA is not meaningful.", ratio="EV/EBITDA")
    flag(r["Debt-to-Equity"] > 10, "Debt-to-Equity above 10x: equity is nearly wiped out.", ratio="Debt-to-Equity")
    flag(raw["Total Equity"] <= 0, "Negative equity: ROE, Debt-to-Equity, Equity Multiplier and P/B left blank.",
         value_col="Total Equity")
    price = raw["Share Price (period end)"]
    repeated = raw.assign(_p=price).duplicated(["Company", "_p"], keep=False) & price.notna()
    flag(repeated, "Same share price as another year for this company: check the price history.",
         value_col="Share Price (period end)")
    cols = ["Company", "Year", "Value", "Issue"]
    return pd.DataFrame(checks, columns=cols).sort_values(["Company", "Year"]).reset_index(drop=True)


def default_data_path() -> Path | None:
    """First workbook/CSV found in the local data/ folder (git-ignored)."""
    folder = Path(__file__).resolve().parent / "data"
    for pattern in ("financials.xlsx", "financials.csv", "*.xlsx", "*.csv"):
        for path in sorted(folder.glob(pattern)):
            if "template" not in path.name:
                return path
    return None


# ==========================================
# 5. PEER COMPARISON, CORRELATION & INDUSTRY ANALYTICS
# ==========================================
def years_of(data_pool: dict[str, dict[str, pd.DataFrame]]) -> list[str]:
    first = next(iter(next(iter(data_pool.values())).values()))
    return [c for c in first.columns if c != "Ratio Category"]


def peer_snapshot(data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, year: str) -> pd.DataFrame:
    """Ratios (rows) × companies (columns) for one industry in one year."""
    return pd.DataFrame({name: df[year] for name, df in data_pool[industry].items()}).astype(float)


def is_favourable(ratio: str, value: float, benchmark: float) -> bool:
    if RATIO_SPECS[ratio].higher_is_better:
        return value >= benchmark
    return value <= benchmark


def peer_percentile(ratio: str, value: float, peer_values: pd.Series) -> float:
    """Share of peers (0-100, among those with a value) the company is at
    least as good as. NaN when the company has no value."""
    peers = peer_values.dropna()
    if pd.isna(value) or peers.empty:
        return float("nan")
    if RATIO_SPECS[ratio].higher_is_better:
        beaten = (peers <= value).sum()
    else:
        beaten = (peers >= value).sum()
    return round(100.0 * beaten / len(peers), 1)


def industry_panel(
    data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, year: str | None = None
) -> pd.DataFrame:
    """One row per (company, year) observation, one column per ratio.

    With ``year`` set, only that year's cross-section of companies is kept.
    """
    frames = []
    for company, df in data_pool[industry].items():
        cols = [year] if year is not None else [c for c in df.columns if c != "Ratio Category"]
        block = df[cols].T.astype(float)
        block.index = pd.MultiIndex.from_product([[company], cols], names=["Company", "Year"])
        frames.append(block)
    panel = pd.concat(frames)
    panel.columns.name = None
    return panel[UNIVERSAL_RATIOS]


MIN_PAIRS = 10  # fewer paired observations than this and r is not reported


def correlation_matrix(panel: pd.DataFrame, method: str = "pearson") -> pd.DataFrame:
    """25 × 25 correlation matrix using all rows where both ratios exist.
    Pairs with too few observations, or a ratio with no variation, are NaN."""
    return panel.corr(method=method, min_periods=MIN_PAIRS)


def pair_counts(panel: pd.DataFrame) -> pd.DataFrame:
    """Number of observations where both ratios have a value."""
    present = panel.notna().astype(int)
    return present.T @ present


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
        return "Correlation cannot be measured: one of the ratios does not vary or has too few values in this sample."
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


def top_correlations(
    corr: pd.DataFrame, include_identities: bool = True, counts: pd.DataFrame | None = None
) -> pd.DataFrame:
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
            row = {
                "Ratio A": a,
                "Ratio B": b,
                "r": round(float(r), 3),
                "Direction": "Move together ↑↑" if r > 0 else "Move opposite ↑↓",
                "Strength": correlation_strength(r),
                "Link": "Linked by formula" if identity else "Economic",
            }
            if counts is not None:
                row["n"] = int(counts.at[a, b])
            rows.append(row)
    cols = ["Ratio A", "Ratio B", "r", "Direction", "Strength", "Link"] + (["n"] if counts is not None else [])
    out = pd.DataFrame(rows, columns=cols)
    return out.reindex(out["r"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def regression_slope(x: pd.Series, y: pd.Series) -> float:
    """Least-squares slope: change in y for a one-unit increase in x."""
    both = pd.concat([x, y], axis=1).dropna()
    if len(both) < 3 or both.iloc[:, 0].nunique() < 2:
        return float("nan")
    return float(np.polyfit(both.iloc[:, 0].astype(float), both.iloc[:, 1].astype(float), 1)[0])


def industry_category_summary(
    data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, category: str, year: str
) -> pd.DataFrame:
    """Distribution of each ratio in a category across the industry's companies."""
    snap = peer_snapshot(data_pool, industry, year).loc[RATIO_CATEGORIES[category]]
    rows = []
    for ratio, values in snap.iterrows():
        v = values.dropna()
        best = "—"
        if v.nunique() > 1:
            best = v.idxmax() if RATIO_SPECS[ratio].higher_is_better else v.idxmin()
        rows.append(
            {
                "Ratio": ratio,
                "Median": v.median(),
                "Mean": v.mean(),
                "P25": v.quantile(0.25),
                "P75": v.quantile(0.75),
                "Min": v.min(),
                "Max": v.max(),
                "Companies": len(v),
                "Best Company": best,
            }
        )
    return pd.DataFrame(rows).set_index("Ratio")


def industry_trend(data_pool: dict[str, dict[str, pd.DataFrame]], industry: str, ratio: str) -> pd.DataFrame:
    """Industry P25 / median / P75 for one ratio, by year."""
    rows = {}
    for year in years_of(data_pool):
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
    the category's ratios (direction-aware). Blank ratios and ratios with no
    variation are skipped."""
    snap = peer_snapshot(data_pool, industry, year).loc[RATIO_CATEGORIES[category]]
    snap = snap[snap.nunique(axis=1) > 1]
    scores = {}
    for company in snap.columns:
        pcts = [peer_percentile(r, snap.at[r, company], snap.loc[r]) for r in snap.index]
        pcts = [p for p in pcts if not np.isnan(p)]
        scores[company] = np.mean(pcts) if pcts else np.nan
    return pd.Series(scores, name=f"{category} Score").dropna().sort_values(ascending=False).round(1)


# ==========================================
# 6. FORMATTING & MATRIX STYLING
# ==========================================
def format_value(ratio: str, value: float) -> str:
    if value is None or pd.isna(value):
        return "—"
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
