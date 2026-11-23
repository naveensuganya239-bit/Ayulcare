import hashlib
from pathlib import Path

from app.services.dataset import DatasetStore

CSV = Path(__file__).resolve().parent.parent / "data" / "original" / "Combined_All_3_CSV_Files.csv"


def test_loads_all_records_and_preserves_original():
    before = hashlib.sha256(CSV.read_bytes()).hexdigest()
    ds = DatasetStore(CSV)
    assert len(ds) == 5649
    assert hashlib.sha256(CSV.read_bytes()).hexdigest() == before  # file untouched
    assert ds.verify_integrity()["intact"]


def test_risk_fallback_and_case_handling():
    ds = DatasetStore(CSV)
    q = ds.quality
    assert q["risk_status_counts"].get("fallback") == 50       # taken from trailing unnamed column
    assert "conflict" not in q["risk_status_counts"]
    assert set(ds.df["risk"].dropna()) == {"Low", "Medium", "High"}   # 'low'/'medium' normalised in memory only
    assert ds.df["risk"].isna().sum() == 0


def test_multiple_remedies_per_problem_preserved():
    ds = DatasetStore(CSV)
    assert max(len(v) for v in ds.groups.values()) > 1
    r = ds.get(1)
    assert r["author"] and r["book"] and r["remedy_ta"]
