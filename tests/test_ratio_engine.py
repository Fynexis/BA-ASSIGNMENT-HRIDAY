from pathlib import Path

import pandas as pd
import pytest

from ratio_engine import (
    HIGHLIGHT_STYLE,
    INDUSTRY_HIGHLIGHTS,
    INSIGHTS_ENGINE,
    RATIO_CATEGORIES,
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


def test_app_renders_for_every_industry():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP_PATH, default_timeout=60).run()
    assert not at.exception
    for industry in INDUSTRY_HIGHLIGHTS:
        at.selectbox[0].select(industry).run()
        assert not at.exception
        assert len(at.metric) == 4
        assert INSIGHTS_ENGINE[industry]["title"] in at.info[0].value
