import math

import pandas as pd

from src.recommendations import recommend

NAN = math.nan


def topic(name, questions, correct, *, level="Exploring", hard=0.0, trend=NAN, recent=NAN, earlier=NAN,
          days_since=1):
    return {
        "subject": "Biology", "chapter": "Ch1", "topic": name, "questions": questions, "correct": correct,
        "accuracy_pct": correct / questions * 100 if questions else NAN, "hard_share_pct": hard,
        "level": level, "days_since": days_since if questions else NAN, "trend_pts": trend,
        "recent_accuracy_pct": recent, "earlier_accuracy_pct": earlier,
    }


def rules(topics, **kwargs):
    recs = recommend(pd.DataFrame(topics), **kwargs)
    return dict(zip(recs["topic"], recs["rule"]))


def test_each_rule_fires_for_its_situation():
    found = rules([
        topic("Declining", 20, 14, trend=-30, recent=50, earlier=80),
        topic("Weak", 10, 3),
        topic("Below pass", 10, 6),
        topic("Few answers", 3, 3),
        topic("Too easy", 10, 9, hard=10),
        topic("Old mastery", 10, 10, level="Mastered", hard=50, days_since=45),
        topic("Never", 0, 0, level="Unexplored"),
        topic("Fine", 10, 9, hard=40),
    ])
    assert found == {
        "Declining": "declining", "Weak": "weak", "Below pass": "below_pass",
        "Few answers": "limited_evidence", "Too easy": "increase_difficulty",
        "Old mastery": "stale", "Never": "unexplored",
    }
    assert "Fine" not in found   # strong, enough hard questions, recent -> nothing to do


def test_one_recommendation_per_topic_highest_priority_wins():
    recs = recommend(pd.DataFrame([topic("Both", 10, 3, trend=-40, recent=10, earlier=50)]))
    assert len(recs) == 1 and recs.iloc[0]["rule"] == "declining"


def test_reasons_quote_the_actual_numbers():
    recs = recommend(pd.DataFrame([topic("Weak", 52, 19)]))
    assert recs.iloc[0]["reason"] == "19 of 52 answers correct (37%), below 50%."


def test_sorted_by_priority_and_inactivity_rule():
    recs = recommend(pd.DataFrame([topic("Never", 0, 0, level="Unexplored"), topic("Weak", 10, 2)]),
                     days_inactive=12)
    assert recs["priority"].tolist() == [1, 1, 3]
    assert recs.iloc[0]["action"] == "Resume regular study"
    assert "12 days" in recs.iloc[0]["reason"]


def test_no_triggers_gives_empty_table():
    recs = recommend(pd.DataFrame([topic("Fine", 10, 9, hard=40)]), days_inactive=2)
    assert recs.empty and "reason" in recs.columns
