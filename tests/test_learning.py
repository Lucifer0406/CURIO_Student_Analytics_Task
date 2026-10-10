from datetime import date, timedelta

import pandas as pd
import pytest

from src import learning


def make_sessions(rows):
    """rows: (start_utc_iso, duration_sec[, kind, activity])"""
    records = []
    for i, row in enumerate(rows):
        start, duration = row[0], row[1]
        kind = row[2] if len(row) > 2 else "learning"
        activity = row[3] if len(row) > 3 else "Topic A"
        ts = pd.Timestamp(start, tz="UTC")
        records.append({"session_id": f"s{i}", "student_id": "x", "kind": kind, "activity": activity,
                        "start": ts, "end": ts + pd.Timedelta(seconds=duration), "duration_sec": float(duration)})
    columns = ["session_id", "student_id", "kind", "activity", "start", "end", "duration_sec"]
    df = pd.DataFrame(records, columns=columns)
    df["start"] = pd.to_datetime(df["start"], utc=True)
    df["end"] = pd.to_datetime(df["end"], utc=True)
    return df


def make_quiz_answers(rows):
    """rows: (attempted_at_utc_iso, status)"""
    df = pd.DataFrame([{"attempt_id": f"q{i}", "attempt_status": status,
                        "attempted_at": pd.Timestamp(ts, tz="UTC")} for i, (ts, status) in enumerate(rows)],
                      columns=["attempt_id", "attempt_status", "attempted_at"])
    df["attempted_at"] = pd.to_datetime(df["attempted_at"], utc=True)
    return df


NO_QUIZZES = make_quiz_answers([])


# --- total_learning_time ---------------------------------------------------
def test_total_learning_time_sums_learning_and_tool_sessions():
    s = make_sessions([("2026-09-01T10:00Z", 600), ("2026-09-01T11:00Z", 300, "tool", "chatbot")])
    assert learning.total_learning_time(s) == 900


def test_total_learning_time_is_zero_without_sessions():
    assert learning.total_learning_time(make_sessions([])) == 0


# --- daily_activity: timezone and activity rules --------------------------------
def test_day_boundaries_use_india_time_not_utc():
    # 19:30 UTC on 1 Sep = 01:00 IST on 2 Sep -> must land on 2 Sep.
    s = make_sessions([("2026-09-01T19:30Z", 600)])
    daily = learning.daily_activity(s, NO_QUIZZES, date(2026, 9, 1), date(2026, 9, 2))
    assert daily.set_index("date").loc[date(2026, 9, 2), "minutes"] == 10
    assert daily.set_index("date").loc[date(2026, 9, 1), "minutes"] == 0


def test_daily_activity_includes_idle_days_and_quiz_only_days():
    s = make_sessions([("2026-09-01T06:00Z", 600)])
    q = make_quiz_answers([("2026-09-03T06:00Z", "completed"), ("2026-09-02T06:00Z", "in_progress")])
    daily = learning.daily_activity(s, q, date(2026, 9, 1), date(2026, 9, 4)).set_index("date")["active"]
    # 1st: session · 2nd: only an abandoned quiz (not active) · 3rd: completed quiz · 4th: nothing
    assert daily.tolist() == [True, False, True, False]


def test_zero_second_sessions_do_not_make_a_day_active():
    s = make_sessions([("2026-09-01T06:00Z", 0)])
    daily = learning.daily_activity(s, NO_QUIZZES, date(2026, 9, 1), date(2026, 9, 1))
    assert not daily["active"].iloc[0]


# --- streaks and consistency -----------------------------------------------
def daily_from_flags(flags, start=date(2026, 9, 1)):
    """A daily_activity-shaped table: one row per day, active where the flag is True."""
    return pd.DataFrame({
        "date": [start + timedelta(days=i) for i in range(len(flags))],
        "minutes": [10.0 if active else 0.0 for active in flags],
        "active": flags,
    })


@pytest.mark.parametrize("flags, expected", [
    ([True, True, True], 3),          # active through as_of
    ([True, True, False], 2),         # grace: as_of not active yet -> count to yesterday
    ([True, False, False], 0),        # broken yesterday -> 0
    ([False, True, True], 2),
    ([], 0),
])
def test_current_streak(flags, expected):
    daily = daily_from_flags(flags)
    as_of = date(2026, 9, 1) + timedelta(days=max(len(flags) - 1, 0))
    assert learning.current_streak(daily, as_of) == expected


def test_longest_streak_finds_the_longest_run_not_the_latest():
    daily = daily_from_flags([True, True, True, False, True, True, False, True])
    assert learning.longest_streak(daily) == 3


def test_consistency_is_share_of_active_days():
    assert learning.consistency_score(daily_from_flags([True, False, True, False])) == 50
    assert learning.consistency_score(daily_from_flags([])) is None


def test_activity_change_compares_two_equal_windows():
    daily = daily_from_flags([True] * 14)            # 10 minutes every day for 2 weeks
    daily.loc[daily.index[-1], "minutes"] = 70       # last day 70 instead of 10
    change = learning.activity_change(daily, as_of=daily["date"].iloc[-1])
    assert change["recent_minutes"] == 130 and change["previous_minutes"] == 70


# --- subject allocation & habits ---------------------------------------------
def test_time_by_subject_maps_topics_and_groups_tools():
    s = make_sessions([("2026-09-01T06:00Z", 600, "learning", "Enthalpy"),
                       ("2026-09-01T07:00Z", 300, "tool", "whiteboard"),
                       ("2026-09-01T08:00Z", 120, "learning", "Something unknown")])
    curriculum = pd.DataFrame({"subject": ["Chemistry"], "chapter": ["Thermodynamics"], "topic": ["Enthalpy"]})
    t = learning.time_by_subject(s, curriculum).set_index("subject")["minutes"]
    assert t.to_dict() == {"Chemistry": 10, "Study tools": 5, "Unmapped": 2}


def test_study_habits_peak_daypart_uses_local_time():
    # 14:00 UTC = 19:30 IST -> evening
    s = make_sessions([("2026-09-01T14:00Z", 1800), ("2026-09-02T14:00Z", 1800)])
    daily = learning.daily_activity(s, NO_QUIZZES, date(2026, 9, 1), date(2026, 9, 2))
    habits = learning.study_habits(s, daily)
    assert habits["peak_daypart"] == "evening"
    assert habits["avg_session_min"] == 30
    assert habits["sessions_per_active_day"] == 1
    assert learning.study_habits(make_sessions([]), daily) is None
