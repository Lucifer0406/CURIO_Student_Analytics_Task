"""Schema-contract tests: whatever the source, the tables look the same."""
import pandas as pd
import pytest

from src.data_loader import (
    ANSWER_COLUMNS, CURRICULUM_COLUMNS, SESSION_COLUMNS,
    load_real, load_synthetic, real_data_available,
)


def check_contract(ds):
    assert list(ds.answers.columns) == ANSWER_COLUMNS
    assert list(ds.sessions.columns) == SESSION_COLUMNS
    assert list(ds.curriculum.columns) == CURRICULUM_COLUMNS
    assert isinstance(ds.answers["attempted_at"].dtype, pd.DatetimeTZDtype)
    assert isinstance(ds.sessions["start"].dtype, pd.DatetimeTZDtype)
    assert ds.answers["is_correct"].dtype == "boolean"
    assert ds.answers["answered"].dtype == "boolean"
    assert set(ds.answers["source"]) <= {"practice", "assessment"}
    assert set(ds.answers["attempt_status"]) <= {"completed", "in_progress"}
    assert set(ds.answers["difficulty"].dropna()) <= {"easy", "medium", "hard"}
    assert set(ds.sessions["kind"]) <= {"learning", "tool"}
    assert (ds.sessions["duration_sec"] >= 0).all()


def test_synthetic_matches_contract():
    ds = load_synthetic()
    check_contract(ds)
    assert ds.students() == ["demo-student-001"]


def test_synthetic_has_planted_edge_cases():
    ds = load_synthetic()
    a = ds.answers
    assert (a["attempt_status"] == "in_progress").any()          # abandoned quiz
    assert (~a["answered"]).any()                                  # blank answers
    assert a.loc[a["source"] == "practice", "time_taken_sec"].isna().all()  # like the real platform
    studied = set(a["topic"])
    assert {"Le Chatelier's Principle", "Ohm's Law"}.isdisjoint(studied)    # unexplored
    assert {"Le Chatelier's Principle", "Ohm's Law"} <= set(ds.curriculum["topic"])


@pytest.mark.skipif(not real_data_available(), reason="CURIO_DATA_DIR not set (real data is local-only)")
def test_real_export_matches_contract():
    ds = load_real()
    check_contract(ds)
    assert len(ds.answers) > 0 and len(ds.sessions) > 0
