from pathlib import Path

import pytest

from app.services.dataset import DatasetStore
from app.services.embeddings import HashingEmbedder
from app.services.retrieval import Query, Retriever, explicit_precautions
from app.services.vectorstore import VectorStore
from app.config import TestingConfig

CSV = Path(__file__).resolve().parent.parent / "data" / "original" / "Combined_All_3_CSV_Files.csv"


@pytest.fixture(scope="module")
def r(tmp_path_factory):
    ds = DatasetStore(CSV)
    emb = HashingEmbedder()
    st = VectorStore(tmp_path_factory.mktemp("idx"), emb, ds.sha256)
    st.ensure(ds.df)
    cfg = {k: getattr(TestingConfig, k) for k in dir(TestingConfig) if k.isupper()}
    return Retriever(ds, st, emb, cfg)


def test_index_reuse(tmp_path):
    ds = DatasetStore(CSV)
    emb = HashingEmbedder()
    VectorStore(tmp_path, emb, ds.sha256).ensure(ds.df)
    st2 = VectorStore(tmp_path, emb, ds.sha256)
    assert st2.load()  # persisted index is reused without re-embedding


def test_all_modes_return_sources(r):
    q = Query(["cough", "sore throat", "fever"], "cough sore throat fever")
    for mode in ("problem_only", "symptom_rag", "proposed"):
        res = r.search(q, mode)
        assert res.items
        rec = r.ds.get(res.items[0]["record_id"])
        assert rec["author"] and rec["book"]


def test_proposed_excludes_dataset_high_and_groups(r):
    res = r.search(Query(["cough"], "cough"), "proposed")
    assert all(r.ds.get(i["record_id"])["risk"] != "High" for i in res.items)
    assert len(res.groups) <= 3


def test_no_match_on_nonsense(r):
    assert r.search(Query([], "zzqx wvvk plorb"), "proposed").no_match


def test_precaution_requires_condition_term():
    assert explicit_precautions("Avoid oily meals and spicy food") == []
    assert "pregnancy" in explicit_precautions("Not recommended during pregnancy")
