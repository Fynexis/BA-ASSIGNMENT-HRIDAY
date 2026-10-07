# PCA & Cluster Analysis of Financial Ratios

Everything is in one Jupyter notebook, **[`analysis.ipynb`](analysis.ipynb)**. It calculates **25 financial ratios** for 100 Indian listed companies (25 each in IT, Pharmaceuticals, FMCG, and Infrastructure / Heavy Manufacturing) over FY2017–FY2026. It then:

1. **groups the ratios** with PCA, to find which ratios measure the same thing, and
2. **groups the companies** with k-means cluster analysis, and compares the clusters with the industries.

All the code, explanations, charts, tables and references are in the notebook, in order.

## Run it in VS Code

1. Install the **Python** and **Jupyter** extensions (both by Microsoft).
2. In the terminal, from this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (Windows)
   source .venv/bin/activate       (Mac/Linux)
   pip install -r requirements.txt
   ```
3. Put your data workbook at **`data/financials.xlsx`**.
4. Open `analysis.ipynb`. Click **Select Kernel** (top right), choose `.venv`, then click **Run All**.

The results appear under each cell. CSV files for jamovi are saved to `output/`.

## Data

The notebook reads a workbook in the layout of [`data/capiq_template.xlsx`](data/capiq_template.xlsx): a `Data` sheet with one row per company per fiscal year and 21 financial line items. `scripts/make_capiq_template.py` rebuilds the template.

**Licensed data stays out of git.** Everything in `data/` except the template, and everything in `output/`, is git-ignored, because Screener and Capital IQ data can't be redistributed. The notebook is saved without outputs for the same reason; run it locally to see the results.

## What the notebook contains

| Section | Contents |
|---|---|
| 1 · Load the data | Reads the workbook and turns "not reported, set to 0" values into missing values. |
| 2 · Calculate the 25 ratios | Every formula is written out in the code. Ratios are left blank where they're not meaningful: P/E with a loss, ROE with negative equity, no inventory reported, and so on. |
| 3 · Prepare the data points | One row per company (the 10-year median of each ratio). Leaves out 4 ratios, fills gaps with the industry median, caps extreme values at the 5th/95th percentile, and standardises. |
| 4 · Grouping the ratios (PCA) | Scree plot, eigenvalue > 1 rule, varimax rotation, loadings table, and each ratio's component compared with its textbook category. |
| 5 · Grouping the companies (k-means) | How the clusters are formed, silhouette scores by k, cluster centres, a map of the companies, a cluster × industry table, ARI against the industries and against Ward clustering, cluster profiles, and every company's scores. |
| 6 · Which ratios separate the industries | Kruskal–Wallis test with eta² for each ratio. |
| 7 · Export for jamovi | CSVs and steps to reproduce the results in jamovi. |
| References | Ratio studies and statistical methods. |

See [`docs/PROJECT_BRIEF.md`](docs/PROJECT_BRIEF.md) for the research questions, the method step by step, and limitations.

## Test

```
pip install -r requirements-dev.txt
pytest -q
```

The test runs the whole notebook on a small made-up dataset and checks the formulas and outputs.
