# PCA & Cluster Analysis of Financial Ratios

A Streamlit app that calculates **25 financial ratios** from company financial statements and then runs **PCA** (grouping the ratios) and **cluster analysis** (grouping the companies). It is built for 100 Indian listed companies (25 each in IT, Pharmaceuticals, FMCG, and Infrastructure / Heavy Manufacturing) over FY2017–FY2026.

## Data

The app reads a workbook in the layout of [`data/capiq_template.xlsx`](data/capiq_template.xlsx): a `Data` sheet with one row per company per fiscal year and 21 financial line items (revenue, net income, total assets, debt, cash flow, share price, market cap and so on).

- **Getting the data:** fill the template with the S&P Capital IQ Excel plug-in, or with figures exported from another source such as Screener.in or CMIE Prowess, keeping the same column names. `scripts/make_capiq_template.py` rebuilds the template.
- **Using it:** save it as `data/financials.xlsx` (or `.csv`), set `FINANCIALS_PATH`, or upload it from the app's sidebar.
- **Licensed data stays out of git.** Everything in `data/` except the template is git-ignored, because data from Capital IQ and Screener can't be redistributed. Keep your data file local.

## What it shows

A single page with three steps:

| Step | Contents |
|---|---|
| **1 · Grouping the ratios (PCA)** | PCA on the ratio correlation matrix (eigenvalue > 1, varimax rotation). Shows a scree plot, the variance explained, and a loadings table, plus which component each ratio belongs to and whether that matches its textbook category. |
| **2 · Grouping the companies (cluster analysis)** | k-means on the component scores. Shows silhouette scores for choosing k, a map of the companies on the first two components, a cluster × industry table with the Adjusted Rand Index, a stability check against Ward clustering, the median ratios for each cluster, and the member list. |
| **3 · Which ratios separate the industries** | A Kruskal–Wallis test with eta² for each ratio. |

CSV downloads and step-by-step jamovi instructions are at the bottom of the page. The analysis code is in `multivariate.py`, and the ratio calculations are in `ratio_engine.py`.

See [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) for the research questions, the method step by step, and how to reproduce the results in jamovi.

## How the ratios are calculated

The formula for each ratio is in `ratio_engine.RATIO_SPECS`. Some ratios are left **blank** rather than given a misleading number:

- **P/E** when the company made a loss
- **ROE, Debt-to-Equity, Equity Multiplier and P/B** when equity is zero or negative
- **Interest coverage** when there is no interest expense
- **Inventory turnover and DIO** when no inventory is reported
- **EV/EBITDA** when EBITDA is zero or negative
- **Any value the data file marks "not reported, set to 0"**, which is treated as missing rather than zero

Correlations use every company-year where both ratios have a value. A pair with fewer than 10 such observations is not reported.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Test

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```

The tests use a small made-up dataset in the same layout, so they don't need the licensed data. They cover:
- the ratio formulas, checked against hand calculations
- the blank-value rules
- reading both .xlsx and .csv files
- the data checks
- the correlation and industry statistics
- a headless run of the app through every industry, category and correlation option
