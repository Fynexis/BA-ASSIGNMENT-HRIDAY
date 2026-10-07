# Cluster & Financial Ratio Analysis Dashboard

A Streamlit dashboard that calculates **25 universal financial ratios** for listed companies from their financial statements. It is built for 100 Indian companies (25 each in IT, Pharmaceuticals, FMCG, and Infrastructure / Heavy Manufacturing) over FY2017–FY2026. For each industry it highlights the 4 ratios that matter most and explains why. It also gives industry statistics and shows how the ratios move together (correlations).

## Data

The dashboard reads a workbook in the layout of [`data/capiq_template.xlsx`](data/capiq_template.xlsx): a `Data` sheet with one row per company per fiscal year and 21 financial line items (revenue, net income, total assets, debt, cash flow, share price, market cap and so on).

- **Getting the data:** fill the template with the S&P Capital IQ Excel plug-in, or with figures exported from another source such as Screener.in or CMIE Prowess, keeping the same column names. `scripts/make_capiq_template.py` rebuilds the template.
- **Using it:** save it as `data/financials.xlsx` (or `.csv`), set `FINANCIALS_PATH`, or upload it from the dashboard's sidebar.
- **Licensed data stays out of git.** Everything in `data/` except the template is git-ignored, because data from Capital IQ and Screener can't be redistributed. Keep your data file local.

## What it shows

| Tab | Contents |
|---|---|
| **Company Matrix** | All 25 ratios × 10 years for one company. The industry's 4 driver ratios are highlighted. Summary tiles show the selected year's value, the change from the previous year and the peer percentile. A reasoning panel explains each driver ratio and compares the company with the industry median. |
| **Industry Stats** | Pick a category (Profitability, Liquidity, …). You get each ratio's median, mean, P25/P75, min/max, how many companies have a value, and the best company; a 10-year industry trend band; a category-score leaderboard; and industry medians side by side. |
| **Ratio Correlations** | A 25 × 25 heatmap (Spearman by default, or Pearson; all years or one year). Also lists the strongest pairs that move together and that move in opposite directions, with how many observations each pair uses. A pair explorer says in plain English what Y does when X goes up, with a scatter plot and slope. A "what moves with this ratio" chart ranks the other 24 ratios. |
| **PCA & Clustering** | **Step 1** groups the *ratios*: PCA (eigenvalue > 1, varimax) gives a scree plot, loadings, and each ratio's component compared with its textbook category. **Step 2** groups the *companies*: k-means on the component scores, with silhouette scores for choosing k, a 2-D map, a cluster × industry table with the Adjusted Rand Index, cluster profiles, and a Ward stability check. **Step 3** runs a Kruskal–Wallis test with eta² to find which ratios separate the industries. A CSV export lets you reproduce it in jamovi. Code: `multivariate.py`. |
| **Data & Checks** | Notes on how the data was cleaned, a list of suspicious values to verify (e.g. dividend yield above 10%, negative equity, EBITDA near zero), the formula for every ratio, and CSV downloads for jamovi or Excel. |

See [docs/PROJECT_BRIEF.md](docs/PROJECT_BRIEF.md) for the research questions, the method step by step, and how to reproduce the results in jamovi.

## How the ratios are calculated

The formula for each ratio is in `ratio_engine.RATIO_SPECS` and in the dashboard's **Data & Checks** tab. Some ratios are left **blank** rather than given a misleading number:

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
