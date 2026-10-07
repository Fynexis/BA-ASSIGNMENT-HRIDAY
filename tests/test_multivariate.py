import numpy as np
import pandas as pd
import pytest

import multivariate as mv
from ratio_engine import load_financials
from tests.test_ratio_engine import INDUSTRIES, N_COMPANIES, make_rows, write_workbook


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    return load_financials(write_workbook(make_rows(), tmp_path_factory.mktemp("d") / "f.xlsx"))


@pytest.fixture(scope="module")
def prep(data):
    return mv.prepare(data)


def test_prepare_one_row_per_company(prep):
    assert prep.z.shape[0] == len(INDUSTRIES) * N_COMPANIES
    assert not prep.z.isna().any().any()
    assert np.allclose(prep.z.mean(), 0) and np.allclose(prep.z.std(ddof=1), 1)
    assert not set(mv.DEFAULT_EXCLUDED) & set(prep.ratios)


def test_winsorising_caps_values(data):
    raw = mv.prepare(data, winsor=0)
    capped = mv.prepare(data, winsor=0.1)
    assert (capped.features.max() <= raw.features.max() + 1e-12).all()
    assert any("capped" in n for n in capped.notes)


def test_varimax_preserves_communalities():
    rng = np.random.default_rng(1)
    loadings = rng.normal(size=(10, 3))
    rotated = mv.varimax(loadings)
    assert np.allclose((loadings**2).sum(axis=1), (rotated**2).sum(axis=1))


def test_pca(prep):
    pca = mv.run_pca(prep)
    assert pca.eigenvalues.sum() == pytest.approx(len(prep.ratios))
    assert pca.n_components == max(int((pca.eigenvalues > 1).sum()), 2)
    assert pca.loadings.shape == (len(prep.ratios), pca.n_components)
    assert set(pca.assignment.index) == set(prep.ratios)
    assert np.allclose(pca.scores.std(ddof=1), 1)
    assert len(mv.component_labels(pca)) == pca.n_components
    assert mv.run_pca(prep, 3).n_components == 3


def test_clustering(prep):
    pca = mv.run_pca(prep)
    clus = mv.cluster_companies(prep, pca, 3)
    assert sorted(clus.labels.unique()) == [1, 2, 3]
    assert clus.crosstab.values.sum() == len(prep.z)
    sizes = clus.labels.value_counts()
    assert sizes[1] >= sizes[2] >= sizes[3]  # numbered by size
    assert -1 <= clus.ari_industry <= 1 and -1 <= clus.ari_ward <= 1
    assert set(clus.silhouette.index) <= set(range(2, 9))
    assert clus.profile_z.shape == (3, len(prep.ratios))


def test_industry_separation(prep):
    sep = mv.industry_separation(prep)
    assert set(sep["Ratio"]) == set(prep.ratios)
    assert sep["eta²"].is_monotonic_decreasing
    assert sep["p-value"].between(0, 1).all()
