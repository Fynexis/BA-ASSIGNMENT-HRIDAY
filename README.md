# Cluster & Financial Ratio Analysis Dashboard

A Streamlit dashboard that shows **25 universal financial ratios** for **100 simulated companies** (4 industries × 25 companies) over **10 years (2017–2026)**. For each industry it highlights the 4 ratios that matter most, and a reasoning engine explains why.

![Dashboard](docs/dashboard.png)

## Features

| Component | Where | What it does |
|---|---|---|
| 25 universal ratios | `ratio_engine.RATIO_SPECS` | 5 categories (Liquidity, Profitability, Efficiency, Leverage, Valuation) × 5 ratios. Each ratio has a unit (`x`, `%`, days), a typical range and a direction (higher or lower is better). |
| 4 industry highlight matrices | `ratio_engine.INDUSTRY_HIGHLIGHTS` | Technology, Retail, Heavy Manufacturing and Banking each light up 4 driver ratios in emerald. The other 21 rows fade to grey. The anchor-year column is tinted. |
| Simulated 10-year data | `ratio_engine.generate_dataset()` | Seeded and reproducible. Each company gets a base level inside its industry's range (`INDUSTRY_PROFILES`, e.g. banks have an 8–15x equity multiplier and no inventory), plus a company-specific drift and a random walk, so trends look plausible. |
| Driver reasoning engine | `ratio_engine.INSIGHTS_ENGINE`, `build_insight_markdown()` | Gives the rationale for each driver ratio, plus the selected company's anchor-year value against the cluster median ("ahead of" / "behind" peers). |
| Scorecards & trends | `app.py` | Shows each driver's anchor-year value, the change from the previous year and the company's percentile among peers. Also draws a 10-year line chart of the company against the cluster median. |

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

The tests cover the ratio and industry definitions, the dataset's shape, bounds, determinism and industry fingerprints, the highlight styling and unit formatting, and a headless `AppTest` render for every industry.
