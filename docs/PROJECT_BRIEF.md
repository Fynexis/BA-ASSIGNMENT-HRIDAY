# Project Brief: Financial Ratio, PCA and Cluster Analysis of 100 Indian Listed Companies

## 1. Research questions

1. How do the four industries differ on 25 standard financial ratios?
2. **Grouping the ratios:** which ratios measure the same underlying financial dimension? (PCA)
3. **Grouping the companies:** do companies with similar financial profiles form clusters, and do those clusters match their industries? (Cluster analysis)

## 2. The two kinds of "clustering", and why they're different

| | Grouping the **ratios** (variables) | Grouping the **companies** (observations) |
|---|---|---|
| Question | Which ratios carry the same information? | Which companies look alike financially? |
| Method | Principal Component Analysis (PCA) with varimax rotation | k-means cluster analysis (Ward hierarchical clustering as a check) |
| Input | Correlation matrix of the ratios | Each company's scores on the PCA components |
| Output | About 6 components, e.g. profitability, liquidity, valuation | k groups of companies with similar profiles |
| Literature | Pinches, Mingo & Caruthers (1973); Chen & Shimerda (1981) | Gupta & Huefner (1972) |

**The order matters: PCA first, then clustering.** Many ratios overlap. ROA, ROE and the net margin all measure profitability, for example. Clustering on all 25 raw ratios would therefore count profitability several times over. Clustering on the component scores gives each financial dimension equal weight.

## 3. Data

- **Sample:** 100 NSE-listed companies, 25 each in IT, Pharmaceuticals, FMCG, and Infrastructure / Heavy Manufacturing.
- **Period:** FY2017–FY2026, March year-ends, consolidated accounts.
- **Source:** Screener.in, laid out in the Capital IQ template format. The data is not stored in this repository.
- **Ratios:** 25 ratios across Liquidity, Profitability, Efficiency, Leverage and Valuation. All formulas are in `ratio_engine.py` (`RATIO_SPECS`).
- **No new data is needed.** One data point should be checked: Vedanta's share price history, which looks inconsistent with its dividends.

## 4. Method, step by step

| Step | What | Why |
|---|---|---|
| 1. Company profile | The median of each ratio over FY2017–FY2026, giving 1 row per company (100 rows). | PCA and clustering need one observation per company. The median isn't distorted by a single bad year. |
| 2. Ratio selection | Drop Inventory Turnover and DIO (most IT firms report no inventory). Drop Receivables Turnover (it duplicates DSO) and Equity Multiplier (it duplicates Debt-to-Equity). That leaves 21 ratios. | Undefined values and ratios that duplicate each other would distort the components. |
| 3. Missing values | Fill with the median of the company's industry (affects 2 values). | PCA needs a complete table. |
| 4. Outliers | Cap each ratio at its 5th and 95th percentiles (winsorising). | Financial ratios are heavily skewed (Lev & Sunder, 1979). Without this, a handful of firms would dominate the components. |
| 5. Standardise | Convert each ratio to a z-score (mean 0, standard deviation 1). | Puts ratios measured in %, x and days on the same scale. |
| 6. PCA | Use the correlation matrix. Keep components with an eigenvalue above 1 (the Kaiser rule) and apply varimax rotation. | These are standard defaults, and jamovi and SPSS use the same ones. |
| 7. Interpret the components | Assign each ratio to the component it loads on most strongly. Compare this with the textbook categories. | This is the "grouping the ratios" answer. |
| 8. Cluster the companies | Run k-means on the component scores. Choose k using the silhouette score, and also run k = 4 to compare with the 4 industries. | This is the "grouping the companies" answer. |
| 9. Validate | Compare clusters with industries using a cluster × industry table and the Adjusted Rand Index (ARI). Check stability by comparing k-means with Ward clustering (also with ARI). | Tests whether financial profiles match industry membership. |
| 10. Industry differences | Run a Kruskal–Wallis test per ratio across the industries, with eta² as the effect size. | Shows which ratios really tell the industries apart. This gives the industry "highlight" ratios a data-based justification. |

## 5. Where each result is in the app

| Report section | Location on the page |
|---|---|
| Data preparation | Notes under the title, and Settings |
| PCA: scree plot, loadings, ratio groups | Step 1 |
| Clusters, cluster × industry table, cluster profiles | Step 2 |
| Ratios that separate the industries | Step 3 |
| Reproducing the results in jamovi | Bottom of the page |

## 6. Reproducing the results in jamovi

1. Download `pca_cluster_data.csv` from the **Reproduce in jamovi** section at the bottom of the page and open it in jamovi.
2. Run **Factor → Principal Component Analysis** on the 21 ratio columns, with eigenvalue > 1 and varimax rotation. The loadings will match, though some signs may be flipped.
3. Install the **snowCluster** module, then run k-means on the PC score columns.
4. Run **ANOVA → One-Way ANOVA (Non-parametric)**, which is the Kruskal–Wallis test, with each ratio by Industry.

## 7. Limitations to state in the report

- Screener doesn't report cost of goods sold or current assets and liabilities directly, so these are estimates. This affects gross margin and the liquidity ratios.
- Inventory-based ratios can't be calculated for most IT companies.
- The PCA and clustering use 10-year medians, so changes over time are deliberately smoothed out. A single year can be chosen in Settings for comparison.
- Cluster results depend on the choices made: which ratios are included, how outliers are capped, and k. The silhouette score and the Ward comparison show how firm the clusters are.
- Correlation and clustering show association, not cause.

## 8. Key references

- Pinches, G. E., Mingo, K. A., & Caruthers, J. K. (1973). The stability of financial patterns in industrial organizations. *Journal of Accounting Research, 11*(2), 389–396.
- Chen, K. H., & Shimerda, T. A. (1981). An empirical analysis of useful financial ratios. *Financial Management, 10*(1), 51–60.
- Gupta, M. C., & Huefner, R. J. (1972). A cluster analysis study of financial ratios and industry characteristics. *Journal of Accounting Research, 10*(1), 77–95.
- Gombola, M. J., & Ketz, J. E. (1983). A note on cash flow and classification patterns of financial ratios. *The Accounting Review, 58*(1), 105–114.
- Johnson, W. B. (1979). The cross-sectional stability of financial ratio patterns. *Journal of Financial and Quantitative Analysis, 14*(5), 1035–1048.
- Salmi, T., Virtanen, I., & Yli-Olli, P. (1990). *On the classification of financial ratios.* Acta Wasaensia No. 25.
- Lev, B., & Sunder, S. (1979). Methodological issues in the use of financial ratios. *Journal of Accounting and Economics, 1*(3), 187–210.
- Bhojraj, S., Lee, C. M. C., & Oler, D. K. (2003). What's my line? A comparison of industry classification schemes for capital market research. *Journal of Accounting Research, 41*(5), 745–774.
