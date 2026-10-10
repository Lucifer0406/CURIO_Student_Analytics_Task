"""Rule-based, explainable recommendations.

Every recommendation is produced by one named rule and carries a `reason`
built from the same numbers the dashboard displays - nothing is inferred
beyond the recorded data. Each topic gets at most ONE recommendation (its
highest-priority rule) so the list stays short and actionable.

Priority: 1 = act now, 2 = soon, 3 = when convenient.
"""
import pandas as pd

from src.config import (
    DECLINE_POINTS, INACTIVE_DAYS, LOW_HARD_SHARE_PCT, MIN_EVIDENCE_QUESTIONS,
    PASS_THRESHOLD_PCT, STALE_DAYS, STRONG_ACCURACY_PCT, TREND_WINDOW_DAYS, WEAK_ACCURACY_PCT,
)


def _pct(value: float) -> str:
    return f"{value:.0f}%"


def _rule_for_topic(t) -> dict | None:
    """Return the highest-priority rule that fires for one topic row, or None."""
    sufficient = t.questions >= MIN_EVIDENCE_QUESTIONS

    if pd.notna(t.trend_pts) and t.trend_pts <= -DECLINE_POINTS:
        return dict(priority=1, rule="declining", action=f"Revisit {t.topic}",
                    reason=f"Accuracy fell from {_pct(t.earlier_accuracy_pct)} to "
                           f"{_pct(t.recent_accuracy_pct)} in the last {TREND_WINDOW_DAYS} days.")
    if sufficient and t.accuracy_pct < WEAK_ACCURACY_PCT:
        return dict(priority=1, rule="weak", action=f"Revise {t.topic}",
                    reason=f"{t.correct} of {t.questions} answers correct ({_pct(t.accuracy_pct)}), "
                           f"below {WEAK_ACCURACY_PCT}%.")
    if sufficient and t.accuracy_pct < PASS_THRESHOLD_PCT:
        return dict(priority=2, rule="below_pass", action=f"Practise {t.topic}",
                    reason=f"{_pct(t.accuracy_pct)} accuracy over {t.questions} questions - "
                           f"under the {PASS_THRESHOLD_PCT}% pass threshold.")
    if 0 < t.questions < MIN_EVIDENCE_QUESTIONS:
        return dict(priority=2, rule="limited_evidence", action=f"Take a quiz on {t.topic}",
                    reason=f"Only {t.questions} question{'s' if t.questions != 1 else ''} answered - "
                           f"not enough to judge (needs {MIN_EVIDENCE_QUESTIONS}).")
    if sufficient and t.accuracy_pct >= STRONG_ACCURACY_PCT and t.hard_share_pct < LOW_HARD_SHARE_PCT:
        return dict(priority=3, rule="increase_difficulty", action=f"Try harder questions in {t.topic}",
                    reason=f"{_pct(t.accuracy_pct)} accuracy, but only {_pct(t.hard_share_pct)} "
                           f"of questions were hard.")
    if t.level == "Mastered" and pd.notna(t.days_since) and t.days_since > STALE_DAYS:
        return dict(priority=3, rule="stale", action=f"Quick review of {t.topic}",
                    reason=f"Mastered, but last practised {int(t.days_since)} days ago.")
    if t.questions == 0:
        return dict(priority=3, rule="unexplored", action=f"Start {t.topic}",
                    reason=f"No attempts yet in {t.chapter} ({t.subject}).")
    return None


def recommend(topics: pd.DataFrame, days_inactive: int | None = None) -> pd.DataFrame:
    """Build the recommendation list from topic_mastery() output.

    days_inactive: days since the last active day (learning.days_since_last_activity);
    adds a study-habit recommendation when it exceeds INACTIVE_DAYS.
    """
    recs = []
    if days_inactive is not None and days_inactive > INACTIVE_DAYS:
        recs.append(dict(priority=1, rule="inactive", topic=None, subject=None,
                         action="Resume regular study",
                         reason=f"No study activity in the last {days_inactive} days."))
    for t in topics.itertuples(index=False):
        rec = _rule_for_topic(t)
        if rec:
            recs.append({**rec, "topic": t.topic, "subject": t.subject})

    columns = ["priority", "action", "reason", "topic", "subject", "rule"]
    if not recs:
        return pd.DataFrame(columns=columns)
    table = pd.DataFrame(recs)[columns]
    return table.sort_values("priority", kind="stable").reset_index(drop=True)
