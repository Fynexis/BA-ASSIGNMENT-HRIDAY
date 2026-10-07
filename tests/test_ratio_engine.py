from pathlib import Path

import pandas as pd
import pytest

from ratio_engine import (
    DERIVED_RATIOS,
    IDENTITY_PAIRS,
    RATIO_CATEGORIES,
    category_scores,
    correlation_matrix,
    cross_industry_medians,
    describe_correlation,
    industry_category_summary,
    industry_panel,
    industry_trend,
    regression_slope,
    top_correlations,
    HIGHLIGHT_STYLE,
    INDUSTRY_HIGHLIGHTS,
    INSIGHTS_ENGINE,
    RATIO_SPECS,
    UNIVERSAL_RATIOS,
    YEARS,
    build_insight_markdown,
    format_value,
    generate_dataset,
    matrix_styles,
    peer_percentile,
    peer_snapshot,
    style_matrix,
)

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")


@pytest.fixture(scope="module")
def pool():
    return generate_dataset()


def test_twenty_five_unique_ratios_in_five_categories():
    assert len(UNIVERSAL_RATIOS) == 25
    assert len(set(UNIVERSAL_RATIOS)) == 25
    assert len(RATIO_CATEGORIES) == 5
    assert all(len(ratios) == 5 for ratios in RATIO_CATEGORIES.values())


def test_four_industries_with_four_valid_highlights():
    assert len(INDUSTRY_HIGHLIGHTS) == 4
    for highlights in INDUSTRY_HIGHLIGHTS.values():
        assert len(highlights) == 4
        assert set(highlights) <= set(UNIVERSAL_RATIOS)


def test_insights_cover_every_highlight():
    assert set(INSIGHTS_ENGINE) == set(INDUSTRY_HIGHLIGHTS)
    for industry, highlights in INDUSTRY_HIGHLIGHTS.items():
        md = build_insight_markdown(industry)
        for ratio in highlights:
            assert INSIGHTS_ENGINE[industry][ratio]
            assert f"**{ratio}**" in md


def test_dataset_shape(pool):
    assert len(YEARS) == 10
    assert sum(len(c) for c in pool.values()) == 100
    for companies in pool.values():
        assert len(companies) == 25
        for df in companies.values():
            assert list(df.index) == UNIVERSAL_RATIOS
            assert list(df.columns) == ["Ratio Category", *YEARS]
            assert (df[YEARS] >= 0).all().all()
            assert df["Ratio Category"].tolist() == [RATIO_SPECS[r].category for r in UNIVERSAL_RATIOS]


def test_dataset_is_deterministic(pool):
    again = generate_dataset()
    for industry, companies in pool.items():
        for name, df in companies.items():
            pd.testing.assert_frame_equal(df, again[industry][name])


def test_industry_profiles_are_distinct(pool):
    def median(industry, ratio):
        return peer_snapshot(pool, industry, YEARS[-1]).loc[ratio].median()

    assert median("Banking / Finance", "Equity Multiplier") > 3 * median("Technology / Software", "Equity Multiplier")
    assert median("Technology / Software", "Gross Profit Margin") > median("Retail / E-Commerce", "Gross Profit Margin")


def test_matrix_styles_highlight_exactly_four_rows(pool):
    industry = "Heavy Manufacturing"
    df = next(iter(pool[industry].values()))
    styles = matrix_styles(df, INDUSTRY_HIGHLIGHTS[industry])
    lit = [r for r in styles.index if (styles.loc[r] == HIGHLIGHT_STYLE).all()]
    assert lit == INDUSTRY_HIGHLIGHTS[industry]
    html = style_matrix(df, INDUSTRY_HIGHLIGHTS[industry], YEARS[0]).to_html()
    assert "Operating Profit Margin" in html


def test_format_value_units():
    assert format_value("Net Profit Margin", 12.345) == "12.35%"
    assert format_value("Debt-to-Equity", 1.5) == "1.50x"
    assert format_value("Days Sales Outstanding (DSO)", 42.06) == "42.1d"


def test_peer_percentile_respects_direction():
    peers = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert peer_percentile("Current Ratio", 4.0, peers) == 100.0
    assert peer_percentile("Debt-to-Equity", 4.0, peers) == 25.0


def test_derived_ratios_follow_accounting_identities(pool):
    df = pool["Banking / Finance"]["Bank Corp 01"][YEARS]
    de, em = df.loc["Debt-to-Equity"], df.loc["Equity Multiplier"]
    assert ((em - (1 + de)).abs() <= 0.011).all()
    roe = df.loc["Return on Assets (ROA)"] * em
    assert ((df.loc["Return on Equity (ROE)"] - roe).abs() <= 0.2).all()
    assert (df.loc["Days Inventory Outstanding (DIO)"] == 0).all()  # banks hold no inventory
    assert set(DERIVED_RATIOS) <= set(UNIVERSAL_RATIOS)
    assert all(p <= set(UNIVERSAL_RATIOS) for p in IDENTITY_PAIRS)


def test_industry_panel_shapes(pool):
    assert industry_panel(pool, "Heavy Manufacturing").shape == (250, 25)
    assert industry_panel(pool, "Heavy Manufacturing", YEARS[-1]).shape == (25, 25)


@pytest.mark.parametrize("industry", list(INDUSTRY_HIGHLIGHTS))
def test_correlations_have_realistic_signs(pool, industry):
    corr = correlation_matrix(industry_panel(pool, industry))
    assert corr.shape == (25, 25)
    assert corr.at["Operating Profit Margin", "Net Profit Margin"] > 0.5
    assert corr.at["Debt-to-Equity", "Interest Coverage Ratio"] < -0.2
    assert corr.at["Receivables Turnover", "Days Sales Outstanding (DSO)"] < -0.8
    assert corr.at["Current Ratio", "Quick Ratio"] > 0.5
    assert corr.at["Price-to-Earnings (P/E)", "Dividend Yield"] < -0.3


def test_constant_ratio_gives_nan_correlation(pool):
    corr = correlation_matrix(industry_panel(pool, "Banking / Finance"))
    assert corr["Inventory Turnover"].isna().all()


def test_top_correlations_sorted_and_identities_filtered(pool):
    corr = correlation_matrix(industry_panel(pool, "Retail / E-Commerce"))
    all_pairs = top_correlations(corr, include_identities=True)
    economic = top_correlations(corr, include_identities=False)
    assert len(all_pairs) == 25 * 24 // 2
    assert (all_pairs["r"].abs().diff().dropna() <= 1e-12).all()
    assert (economic["Link"] == "Economic").all()
    assert len(all_pairs) - len(economic) == len(IDENTITY_PAIRS)


def test_describe_correlation_wording():
    assert "go **up** too" in describe_correlation("A", "B", 0.8)
    assert "go **down**" in describe_correlation("A", "B", -0.5)
    assert "independently" in describe_correlation("A", "B", 0.05)
    assert "cannot be measured" in describe_correlation("A", "B", float("nan"))


def test_regression_slope():
    x = pd.Series([1.0, 2.0, 3.0])
    assert regression_slope(x, 2 * x + 1) == pytest.approx(2.0)
    assert pd.isna(regression_slope(pd.Series([1.0, 1.0]), pd.Series([1.0, 2.0])))


def test_industry_stats(pool):
    year = YEARS[-1]
    summary = industry_category_summary(pool, "Technology / Software", "Profitability", year)
    assert list(summary.index) == RATIO_CATEGORIES["Profitability"]
    assert (summary["P25"] <= summary["Median"]).all() and (summary["Median"] <= summary["P75"]).all()
    trend = industry_trend(pool, "Technology / Software", "Net Profit Margin")
    assert list(trend.index) == YEARS
    cross = cross_industry_medians(pool, "Leverage", year)
    assert list(cross.columns) == list(INDUSTRY_HIGHLIGHTS)
    assert cross.at["Equity Multiplier", "Banking / Finance"] > cross.at["Equity Multiplier", "Technology / Software"]
    scores = category_scores(pool, "Retail / E-Commerce", "Profitability", year)
    assert len(scores) == 25 and scores.between(0, 100).all()
    assert scores.is_monotonic_decreasing


def test_app_renders_for_every_industry():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    for industry in INDUSTRY_HIGHLIGHTS:
        at.selectbox[0].select(industry).run()
        assert not at.exception
        assert len(at.metric) == 4
        assert INSIGHTS_ENGINE[industry]["title"] in at.info[0].value
    # Industry stats & correlation controls
    for category in RATIO_CATEGORIES:
        at.radio[0].set_value(category).run()
        assert not at.exception
    at.radio[1].set_value(at.radio[1].options[1]).run()  # single-year scope
    at.radio[2].set_value("Spearman").run()
    at.toggle[0].set_value(True).run()
    assert not at.exception
