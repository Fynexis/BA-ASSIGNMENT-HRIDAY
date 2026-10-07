"""Financial ratios: definitions and calculation from company financials.

The 25 universal ratio definitions and the loader that turns a company
financials workbook (layout of data/capiq_template.xlsx) into those ratios.
Kept free of Streamlit so it can be tested on its own.
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

# ==========================================
# 2. DATA LOADER: FINANCIALS → 25 RATIOS
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
    return FinancialData(raw=raw, ratios=ratios, years=years, issues=issues)


def default_data_path() -> Path | None:
    """First workbook/CSV found in the local data/ folder (git-ignored)."""
    folder = Path(__file__).resolve().parent / "data"
    for pattern in ("financials.xlsx", "financials.csv", "*.xlsx", "*.csv"):
        for path in sorted(folder.glob(pattern)):
            if "template" not in path.name:
                return path
    return None
