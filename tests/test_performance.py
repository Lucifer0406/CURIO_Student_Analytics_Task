import pandas as pd
import pytest

from src.data_loader import load_synthetic
from src.performance import (
    accuracy_table, attempt_history, badge_status, completed_quiz_count, overall_accuracy,
    progress_over_time, response_time_vs_accuracy,
)


def make_answers(statuses, results, attempt_ids=None, sources=None):
    """Tiny `answers` table with only the columns the performance functions need.

    attempt_ids / sources are optional so the overall_accuracy tests stay short:
    by default every row is its own practice attempt.
    """
    n = len(statuses)
    return pd.DataFrame({
        "attempt_id": attempt_ids if attempt_ids is not None else [f"a{i}" for i in range(n)],
        "source": sources if sources is not None else ["practice"] * n,
        "attempt_status": statuses,
        "is_correct": pd.array(results, dtype="boolean"),
    })


# ---------------------------------------------------------------------------
# overall_accuracy
# ---------------------------------------------------------------------------
def test_accuracy_is_pooled_over_completed_answers():
    answers = make_answers(["completed"] * 4, [True, False, True, True])
    assert overall_accuracy(answers) == pytest.approx(75.0)


def test_in_progress_ignored():
    answers = make_answers(["completed","completed","in_progress","in_progress"],[True,False,True,True])
    assert overall_accuracy(answers) == pytest.approx(50)


def test_empty_table():
    answers = make_answers([],[])
    assert overall_accuracy(answers) is None


def test_completed_is_correct_NA():
    answers = make_answers(['completed']*4,[None]*4)
    assert overall_accuracy(answers) is None


# ---------------------------------------------------------------------------
# overall_accuracy - edge cases
# ---------------------------------------------------------------------------
def test_accuracy_pools_answers_instead_of_averaging_quizzes():
    # Quiz A: 1/2 correct (50%). Quiz B: 10/10 correct (100%).
    # Pooled: 11/12 = 91.67%.  Mean of quiz %s would be 75% -> must NOT be that.
    answers = make_answers(
        ["completed"] * 12,
        [True, False] + [True] * 10,
        attempt_ids=["A", "A"] + ["B"] * 10,
    )
    assert overall_accuracy(answers) == pytest.approx(11 / 12 * 100)


def test_not_evaluated_answers_are_excluded_not_counted_wrong():
    # [True, <NA>, False]: excluding <NA> gives 1/2 = 50%; counting it wrong gives 33%.
    answers = make_answers(["completed"] * 3, [True, None, False])
    assert overall_accuracy(answers) == pytest.approx(50.0)


def test_only_in_progress_attempts_gives_none():
    answers = make_answers(["in_progress"] * 3, [True, True, False])
    assert overall_accuracy(answers) is None


@pytest.mark.parametrize("results, expected", [
    ([True, True, True], 100.0),    # upper bound reachable
    ([False, False, False], 0.0),   # a real 0% is still a number, not None
])
def test_accuracy_bounds(results, expected):
    answers = make_answers(["completed"] * 3, results)
    assert overall_accuracy(answers) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# completed_quiz_count
# ---------------------------------------------------------------------------
def test_quiz_count_counts_attempts_not_question_rows():
    # 2 completed attempts x 3 questions + 1 in-progress attempt.
    # Row-counting bug -> 6 (or 9);  missing status filter -> 3.
    answers = make_answers(
        ["completed"] * 6 + ["in_progress"] * 3,
        [True] * 9,
        attempt_ids=["q1"] * 3 + ["q2"] * 3 + ["q3"] * 3,
    )
    assert completed_quiz_count(answers) == 2


def test_quiz_count_includes_practice_and_assessments():
    # Documented decision: both sources count toward badges.
    answers = make_answers(
        ["completed"] * 4,
        [True] * 4,
        attempt_ids=["pq1", "pq1", "as1", "as1"],
        sources=["practice", "practice", "assessment", "assessment"],
    )
    assert completed_quiz_count(answers) == 2


def test_quiz_count_attempt_with_unevaluated_answers_still_counts():
    # Finished but not graded yet is still a completed quiz.
    answers = make_answers(["completed"] * 2, [None, None], attempt_ids=["q1", "q1"])
    assert completed_quiz_count(answers) == 1


@pytest.mark.parametrize("statuses", [[], ["in_progress", "in_progress"]])
def test_quiz_count_is_zero_when_nothing_completed(statuses):
    answers = make_answers(statuses, [True] * len(statuses), attempt_ids=["q1"] * len(statuses))
    result = completed_quiz_count(answers)
    assert result == 0
    assert isinstance(result, int)  # 0, not None: zero quizzes is a real count


# ---------------------------------------------------------------------------
# Regression check on the seeded synthetic student
# ---------------------------------------------------------------------------
def test_synthetic_demo_student_numbers():
    # 24 completed practice + 4 assessments; 1 abandoned practice attempt excluded.
    # If this fails after regenerating synthetic data, re-check the numbers by hand.
    answers = load_synthetic().answers
    assert completed_quiz_count(answers) == 28
    assert 0 <= overall_accuracy(answers) <= 100


# ---------------------------------------------------------------------------
# Breakdowns, progression, response time, badges
# ---------------------------------------------------------------------------
def make_full(rows):
    """rows: (attempt_id, status, attempted_at_utc, subject, difficulty, is_correct, time_sec, answered)"""
    df = pd.DataFrame(rows, columns=["attempt_id", "attempt_status", "attempted_at", "subject", "difficulty",
                                     "is_correct", "time_taken_sec", "answered"])
    df["attempted_at"] = pd.to_datetime(df["attempted_at"], utc=True)
    df["is_correct"] = df["is_correct"].astype("boolean")
    df["answered"] = df["answered"].astype("boolean")
    df["time_taken_sec"] = df["time_taken_sec"].astype(float)
    df["source"] = "assessment"
    df["topic"] = df["subject"]
    return df


FULL = make_full([
    ("a1", "completed", "2026-09-01T06:00Z", "Physics", "easy", True, 20, True),
    ("a1", "completed", "2026-09-01T06:00Z", "Physics", "hard", False, 130, True),
    ("a1", "completed", "2026-09-01T06:00Z", None, "medium", True, 45, True),
    ("a2", "completed", "2026-09-20T06:00Z", "Biology", "easy", True, 25, True),
    ("a2", "completed", "2026-09-20T06:00Z", "Biology", "easy", False, 5, False),   # blank
    ("a3", "in_progress", "2026-09-21T06:00Z", "Biology", "easy", True, 10, True),  # ignored
])


def test_accuracy_table_groups_and_labels_missing_values():
    t = accuracy_table(FULL, "subject").set_index("subject")
    assert t.loc["Physics", "questions"] == 2 and t.loc["Physics", "accuracy_pct"] == 50
    assert t.loc["Biology", "questions"] == 2          # blank counts, in-progress doesn't
    assert t.loc["Unmapped", "questions"] == 1         # missing subject kept, not dropped
    assert t["questions"].sum() == 5                   # adds up to overall_accuracy's denominator


def test_progress_over_time_monthly_and_empty_periods_omitted():
    t = progress_over_time(FULL, "M")
    assert len(t) == 1 and t.iloc[0]["questions"] == 5 and t.iloc[0]["accuracy_pct"] == 60
    weekly = progress_over_time(FULL, "W")
    assert len(weekly) == 2                            # two weeks with quizzes, none in between


def test_attempt_history_one_row_per_completed_attempt():
    t = attempt_history(FULL)
    assert t["attempt_id"].tolist() == ["a1", "a2"]
    assert t["accuracy_pct"].round(1).tolist() == [66.7, 50.0]


def test_response_time_bands_exclude_blanks():
    t = response_time_vs_accuracy(FULL).set_index("time_band")["questions"].to_dict()
    assert t == {"< 30 s": 2, "30–60 s": 1, "> 2 min": 1}   # the 5 s blank is excluded


@pytest.mark.parametrize("count, current, nxt, remaining", [
    (0, None, "Bronze Scholar", 5),
    (5, "Bronze Scholar", "Silver Achiever", 10),
    (28, "Silver Achiever", "Gold Legend", 2),
    (30, "Gold Legend", None, 0),
])
def test_badge_status(count, current, nxt, remaining):
    assert badge_status(count) == {"current": current, "next": nxt, "remaining": remaining}
