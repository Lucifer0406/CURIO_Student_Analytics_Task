"""Learning time & streak calculator (architecture: "Learning Time & Streak Calculator").

Input: the `sessions` table (and `answers` for activity days) from
src/data_loader.py, already filtered to one student.

Day boundaries use LOCAL_TIMEZONE, not UTC: a session at 23:30 IST on the 5th
is stored as 18:00 UTC on the 5th, but one at 01:00 IST on the 6th is stored as
19:30 UTC on the 5th - grouping by UTC date would put it on the wrong day.
"""
from datetime import date, timedelta

import pandas as pd

from src.config import LOCAL_TIMEZONE


def local_dates(timestamps: pd.Series) -> pd.Series:
    """UTC timestamps -> calendar dates in the student's timezone."""
    return timestamps.dt.tz_convert(LOCAL_TIMEZONE).dt.date


def total_learning_time(sessions: pd.DataFrame) -> float:
    """Total study seconds: learning + tool sessions. 0 if none.

    Uses duration_sec (excludes pauses) rather than end - start. 0-second
    sessions are dropped; that doesn't change the sum but keeps the rule
    identical to session counts and averages elsewhere.
    """
    durations = sessions["duration_sec"]
    return float(durations[durations > 0].sum())


def daily_activity(sessions: pd.DataFrame, answers: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    """One row per local calendar day from start to end (inclusive), including idle days.

    columns: date, minutes, sessions, quizzes, active
    A day is ACTIVE if it has any study time or any completed quiz/assessment.
    """
    days = pd.DataFrame({"date": [start + timedelta(days=i) for i in range((end - start).days + 1)]})

    real = sessions[sessions["duration_sec"] > 0]
    per_day_sessions = (
        real.assign(date=local_dates(real["start"]))
        .groupby("date")
        .agg(minutes=("duration_sec", lambda s: s.sum() / 60), sessions=("session_id", "nunique"))
    )
    done = answers[answers["attempt_status"] == "completed"]
    per_day_quizzes = (
        done.assign(date=local_dates(done["attempted_at"]))
        .groupby("date")
        .agg(quizzes=("attempt_id", "nunique"))
    )
    table = days.join(per_day_sessions, on="date").join(per_day_quizzes, on="date")
    table = table.fillna({"minutes": 0.0, "sessions": 0, "quizzes": 0})
    table["sessions"] = table["sessions"].astype(int)
    table["quizzes"] = table["quizzes"].astype(int)
    table["active"] = (table["minutes"] > 0) | (table["quizzes"] > 0)
    return table


def current_streak(daily: pd.DataFrame, as_of: date) -> int:
    """Consecutive active days ending on as_of.

    Grace rule: if as_of itself is not active yet (the day isn't over), the
    streak is counted up to the day before instead of resetting to 0.
    """
    active = set(daily.loc[daily["active"], "date"])
    day = as_of if as_of in active else as_of - timedelta(days=1)
    streak = 0
    while day in active:
        streak += 1
        day -= timedelta(days=1)
    return streak


def longest_streak(daily: pd.DataFrame) -> int:
    """Longest run of consecutive active days in the table."""
    best = run = 0
    previous = None
    for day in sorted(daily.loc[daily["active"], "date"]):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, run)
        previous = day
    return best


def consistency_score(daily: pd.DataFrame) -> float | None:
    """Active days / days in the period * 100. None for an empty period.

    PROTOTYPE definition: the architecture names a "Consistency Score (%)"
    without a formula. Share of active days is the simplest explainable one.
    """
    if daily.empty:
        return None
    return float(daily["active"].mean() * 100)


def weekly_minutes(daily: pd.DataFrame) -> pd.DataFrame:
    """Study minutes and active days per Monday-starting week."""
    if daily.empty:
        return pd.DataFrame(columns=["week_start", "minutes", "active_days"])
    week_start = pd.to_datetime(daily["date"]).dt.to_period("W-SUN").dt.start_time
    return (
        daily.assign(week_start=week_start)
        .groupby("week_start")
        .agg(minutes=("minutes", "sum"), active_days=("active", "sum"))
        .reset_index()
    )


def activity_change(daily: pd.DataFrame, as_of: date, window_days: int = 7) -> dict:
    """Study minutes in the last `window_days` vs the window before it."""
    recent_start = as_of - timedelta(days=window_days - 1)
    previous_start = recent_start - timedelta(days=window_days)
    in_recent = daily["date"].between(recent_start, as_of)
    in_previous = daily["date"].between(previous_start, recent_start - timedelta(days=1))
    recent = float(daily.loc[in_recent, "minutes"].sum())
    previous = float(daily.loc[in_previous, "minutes"].sum())
    return {"recent_minutes": recent, "previous_minutes": previous, "change_minutes": recent - previous}


def days_since_last_activity(daily: pd.DataFrame, as_of: date) -> int | None:
    active = daily.loc[daily["active"] & (daily["date"] <= as_of), "date"]
    return (as_of - active.max()).days if len(active) else None


def time_by_subject(sessions: pd.DataFrame, curriculum: pd.DataFrame) -> pd.DataFrame:
    """Study minutes per subject.

    Learning sessions are mapped to a subject through their topic title in the
    curriculum; tool sessions (chatbot, whiteboard, ...) are grouped as
    "Study tools"; topics not found in the curriculum become "Unmapped".
    """
    real = sessions[sessions["duration_sec"] > 0]
    if real.empty:
        return pd.DataFrame(columns=["subject", "minutes", "sessions"])
    topic_to_subject = curriculum.drop_duplicates("topic").set_index("topic")["subject"]
    subject = real["activity"].map(topic_to_subject).fillna("Unmapped")
    subject = subject.where(real["kind"] != "tool", "Study tools")
    return (
        real.assign(subject=subject)
        .groupby("subject")
        .agg(minutes=("duration_sec", lambda s: s.sum() / 60), sessions=("session_id", "nunique"))
        .reset_index()
        .sort_values("minutes", ascending=False)
        .reset_index(drop=True)
    )


DAYPARTS = [(5, 12, "morning"), (12, 17, "afternoon"), (17, 21, "evening"), (21, 29, "night")]


def _daypart(hour: int) -> str:
    hour = hour if hour >= 5 else hour + 24          # 00:00-04:59 belongs to "night"
    return next(name for start, end, name in DAYPARTS if start <= hour < end)


def study_habits(sessions: pd.DataFrame, daily: pd.DataFrame) -> dict | None:
    """Computed behaviour facts (not AI text). None when there are no sessions.

    avg_session_min        mean length of non-zero sessions
    sessions_per_active_day
    peak_daypart           part of the local day with the most study minutes
    peak_daypart_share     % of study minutes in that part of the day
    weekend_share_pct      % of study minutes on Saturday/Sunday
    """
    real = sessions[sessions["duration_sec"] > 0]
    if real.empty:
        return None
    local = real["start"].dt.tz_convert(LOCAL_TIMEZONE)
    minutes = real["duration_sec"] / 60
    by_part = minutes.groupby(local.dt.hour.map(_daypart)).sum()
    active_days = int(daily["active"].sum()) or 1
    return {
        "avg_session_min": float(minutes.mean()),
        "sessions_per_active_day": len(real) / active_days,
        "peak_daypart": by_part.idxmax(),
        "peak_daypart_share": float(by_part.max() / minutes.sum() * 100),
        "weekend_share_pct": float(minutes[local.dt.dayofweek >= 5].sum() / minutes.sum() * 100),
    }
