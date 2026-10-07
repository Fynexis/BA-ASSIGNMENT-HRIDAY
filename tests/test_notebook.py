"""Runs analysis.ipynb end to end on a small made-up dataset in the same
layout as the real workbook, so the test never needs the licensed data."""

from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
from nbclient import NotebookClient
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent.parent
INDUSTRIES = ["Technology / Software", "FMCG", "Pharmaceuticals"]
YEARS = ["FY2024", "FY2025", "FY2026"]
N_COMPANIES = 12


def make_rows() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for industry in INDUSTRIES:
        for c in range(N_COMPANIES):
            for y in YEARS:
                rev = rng.uniform(1_000, 10_000)
                cogs = rev * rng.uniform(0.3, 0.7)
                ebitda = rev * rng.uniform(0.1, 0.3)
                ebit = ebitda * 0.8
                equity = rng.uniform(2_000, 8_000)
                debt = equity * rng.uniform(0.0, 1.5)
                interest = debt * 0.08
                ni = (ebit - interest) * 0.75
                assets = equity + debt + rng.uniform(500, 2_000)
                price = rng.uniform(100, 1_000)
                mcap = ni * rng.uniform(10, 40)
                rows.append(
                    {
                        "Industry": industry,
                        "Company": f"{industry.split()[0]} Co {c:02d}",
                        "Capital IQ Ticker": f"NSEI:X{c}",
                        "Period": y,
                        "Period End Date": pd.Timestamp(f"{y[2:]}-03-31"),
                        "Total Revenue": rev,
                        "Cost of Goods Sold": cogs,
                        "Gross Profit": rev - cogs,
                        "EBIT": ebit,
                        "EBITDA": ebitda,
                        "Interest Expense": interest,
                        "Net Income": ni,
                        "Total Current Assets": assets * 0.5,
                        "Total Current Liabilities": assets * rng.uniform(0.2, 0.4),
                        "Cash & ST Investments": assets * 0.1,
                        "Inventory": cogs * rng.uniform(0.05, 0.3),
                        "Total Receivables": rev * rng.uniform(0.1, 0.3),
                        "Total Assets": assets,
                        "Total Debt": debt,
                        "Total Equity": equity,
                        "Cash from Operations": ebitda * 0.7,
                        "Debt Repaid": debt * 0.1,
                        "Dividend per Share": price * rng.uniform(0.0, 0.03),
                        "Share Price (period end)": price,
                        "Market Cap": mcap,
                        "Total Enterprise Value": mcap + debt,
                        "Notes": None,
                    }
                )
    df = pd.DataFrame(rows)
    # Special cases the loader must handle
    first = df.index[(df["Company"] == "Technology Co 00") & (df["Period"] == "FY2026")][0]
    df.loc[first, ["Inventory", "Debt Repaid"]] = 0
    df.loc[first, "Notes"] = "Not reported on Screener, set to 0: inventory, debt repaid"
    loss = df.index[(df["Company"] == "Technology Co 01") & (df["Period"] == "FY2026")][0]
    df.loc[loss, "Net Income"] = -500
    neg_eq = df.index[(df["Company"] == "FMCG Co 00") & (df["Period"] == "FY2025")][0]
    df.loc[neg_eq, "Total Equity"] = -100
    no_int = df.index[(df["Company"] == "FMCG Co 01") & (df["Period"] == "FY2024")][0]
    df.loc[no_int, ["Interest Expense", "Total Debt"]] = 0
    big_div = df.index[(df["Company"] == "FMCG Co 02") & (df["Period"] == "FY2024")][0]
    df.loc[big_div, "Dividend per Share"] = df.loc[big_div, "Share Price (period end)"] * 0.5
    return df


def write_workbook(df: pd.DataFrame, path: Path) -> Path:
    """Same layout as the real file: note row, header row, mnemonic row, data."""
    wb = Workbook()
    wb.active.title = "Instructions"
    ws = wb.create_sheet("Data")
    ws.append(["Test data"])
    ws.append(list(df.columns))
    ws.append([None] * 5 + [f"IQ_{i}" for i in range(len(df.columns) - 5)])
    for row in df.itertuples(index=False):
        ws.append([None if (isinstance(v, float) and np.isnan(v)) else v for v in row])
    wb.save(path)
    return path


def test_notebook_runs(tmp_path, monkeypatch):
    data = write_workbook(make_rows(), tmp_path / "financials.xlsx")
    out = tmp_path / "output"
    monkeypatch.setenv("FINANCIALS_PATH", str(data))
    monkeypatch.setenv("OUTPUT_DIR", str(out))
    monkeypatch.setenv("MPLBACKEND", "Agg")
    nb = nbformat.read(ROOT / "analysis.ipynb", as_version=4)
    NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}}).execute()

    errors = [o for c in nb.cells if c.cell_type == "code" for o in c.outputs if o.output_type == "error"]
    assert not errors
    text = "\n".join(o.get("text", "") for c in nb.cells if c.cell_type == "code" for o in c.outputs)
    assert f"{len(INDUSTRIES) * N_COMPANIES} companies" in text
    assert "2 'not reported' values treated as missing" in text  # one note listing 2 items
    assert "Components kept" in text

    export = pd.read_csv(out / "pca_cluster_data.csv")
    assert len(export) == len(INDUSTRIES) * N_COMPANIES
    assert set(export["Cluster"]) == {1, 2, 3, 4}
    ratios = pd.read_csv(out / "ratios_by_company_year.csv")
    assert len(ratios) == len(INDUSTRIES) * N_COMPANIES * len(YEARS)
    # Spot-check one formula against the raw data
    raw = make_rows()
    row = raw[(raw["Company"] == "FMCG Co 05") & (raw["Period"] == "FY2025")].iloc[0]
    got = ratios[(ratios["Company"] == "FMCG Co 05") & (ratios["Year"] == "FY2025")].iloc[0]
    assert np.isclose(got["Current Ratio"], row["Total Current Assets"] / row["Total Current Liabilities"], rtol=1e-3)
    # Loss year -> P/E blank; negative equity -> ROE blank
    loss = ratios[(ratios["Company"] == "Technology Co 01") & (ratios["Year"] == "FY2026")].iloc[0]
    assert pd.isna(loss["Price-to-Earnings (P/E)"])
    neg = ratios[(ratios["Company"] == "FMCG Co 00") & (ratios["Year"] == "FY2025")].iloc[0]
    assert pd.isna(neg["Return on Equity (ROE)"])
