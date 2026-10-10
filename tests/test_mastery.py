from datetime import date

import pandas as pd
import pytest

from src.mastery import mastery_level, mastery_score, recency_component, topic_mastery

AS_OF = date(2026, 10, 1)
CURRICULUM = pd.DataFrame({
    "subject": ["Biology", "Biology", "Physics"],
    "chapter": ["Ch1", "Ch1", "Ch2"],
    "topic": ["Strong", "Weak", "Never"],
})


def answers_for(topic, results, difficulty="medium", when="2026-09-30T06:00Z", status="completed",
                subject="Biology"):
    n = len(results)
    return pd.DataFrame({
        "attempt_id": [f"{topic}-{when}"] * n, "student_id": ["x"] * n, "source": ["practice"] * n,
        "attempt_status": [status] * n, "attempted_at": pd.to_datetime([when] * n, utc=True),
        "subject": [subject] * n, "chapter": ["Ch1"] * n, "topic": [topic] * n,
        "difficulty": [difficulty] * n, "answered": pd.array([True] * n, dtype="boolean"),
        "is_correct": pd.array(results, dtype="boolean"), "time_taken_sec": [30.0] * n,
    })


def row(table, topic):
    return table.set_index("topic").loc[topic]


# --- the formula itself -------------------------------------------------------
def test_recency_halves_every_half_life():
    assert recency_component(0) == 1
    assert recency_component(21) == pytest.approx(0.5)
    assert recency_component(42) == pytest.approx(0.25)


def test_mastery_score_uses_manager_weights():
    assert mastery_score(1, 1, 1) == pytest.approx(100)
    assert mastery_score(1, 0, 0) == pytest.approx(60)
    assert mastery_score(0, 1, 0) == pytest.approx(25)
    assert mastery_score(0, 0, 1) == pytest.approx(15)


@pytest.mark.parametrize("score, questions, level", [
    (90, 10, "Mastered"),
    (90, 4, "Exploring"),      # high score but too little evidence
    (69.9, 50, "Exploring"),
    (float("nan"), 0, "Unexplored"),
])
def test_mastery_level_rules(score, questions, level):
    assert mastery_level(score, questions) == level


# --- topic_mastery end to end ---------------------------------------------------
def test_worked_example_matches_hand_calculation():
    # 8 medium questions, 6 correct, last attempt 1 day before AS_OF.
    a = answers_for("Strong", [True] * 6 + [False] * 2)
    t = row(topic_mastery(a, CURRICULUM, AS_OF), "Strong")
    accuracy = 6 / 8
    difficulty = 6 * (2 / 3) / 8
    recency = 0.5 ** (1 / 21)
    assert t["mastery_score"] == pytest.approx(100 * (0.6 * accuracy + 0.25 * difficulty + 0.15 * recency))
    assert t["mastery_score"] == pytest.approx(72.0, abs=0.1)   # 45 + 12.5 + 14.5
    assert t["level"] == "Mastered"                             # >= 70 with 8 questions


def test_wrong_hard_answers_earn_no_difficulty_credit():
    a = answers_for("Weak", [False] * 6, difficulty="hard")
    t = row(topic_mastery(a, CURRICULUM, AS_OF), "Weak")
    assert t["difficulty_component"] == 0
    assert t["accuracy_component"] == 0


def test_never_attempted_curriculum_topic_is_unexplored():
    t = row(topic_mastery(answers_for("Strong", [True] * 5), CURRICULUM, AS_OF), "Never")
    assert t["level"] == "Unexplored" and t["questions"] == 0 and t["evidence"] == "none"
    assert pd.isna(t["mastery_score"])


def test_in_progress_and_future_answers_are_ignored():
    a = pd.concat([
        answers_for("Strong", [True] * 5),
        answers_for("Strong", [False] * 5, status="in_progress", when="2026-09-29T06:00Z"),
        answers_for("Strong", [False] * 5, when="2026-10-05T06:00Z"),   # after AS_OF
    ])
    t = row(topic_mastery(a, CURRICULUM, AS_OF), "Strong")
    assert t["questions"] == 5 and t["accuracy_pct"] == 100


def test_attempted_topic_outside_curriculum_still_appears():
    a = answers_for("Extra topic", [True, False, True, True, True])
    assert "Extra topic" in set(topic_mastery(a, CURRICULUM, AS_OF)["topic"])


def test_trend_compares_recent_window_with_earlier_answers():
    a = pd.concat([
        answers_for("Strong", [True] * 4, when="2026-08-01T06:00Z"),   # earlier: 100%
        answers_for("Strong", [True, False, False, False], when="2026-09-25T06:00Z"),  # recent: 25%
    ])
    t = row(topic_mastery(a, CURRICULUM, AS_OF), "Strong")
    assert t["earlier_accuracy_pct"] == 100 and t["recent_accuracy_pct"] == 25
    assert t["trend_pts"] == -75


def test_trend_needs_enough_questions_in_both_windows():
    a = pd.concat([answers_for("Strong", [True] * 3, when="2026-08-01T06:00Z"),
                   answers_for("Strong", [False] * 4, when="2026-09-25T06:00Z")])
    assert pd.isna(row(topic_mastery(a, CURRICULUM, AS_OF), "Strong")["trend_pts"])


def test_empty_answers_give_only_unexplored_topics():
    empty = answers_for("Strong", []).iloc[0:0]
    t = topic_mastery(empty, CURRICULUM, AS_OF)
    assert set(t["level"]) == {"Unexplored"} and len(t) == 3
