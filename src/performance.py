"""Accuracy & progression engine (architecture: "Attempt & Accuracy Engine",
"Progression Aggregation", "Subject Performance Normalizer", "Achievement Badges").

Input: the `answers` table from src/data_loader.py, already filtered to one
student. Every percentage here uses the same denominator as overall_accuracy:
evaluated answers (is_correct known) in completed attempts. Blanks count as
wrong; not-yet-graded answers are excluded.
"""
import pandas as pd

from src.config import BADGES, LOCAL_TIMEZONE


# --- Written by the intern (Stage 2) ----------------------------------------
def overall_accuracy(answers: pd.DataFrame) -> float | None:
    """Pooled % of evaluated answers in completed attempts. None if nothing to measure."""
    completed = answers[answers['attempt_status']=='completed']
    known_status = completed[completed['is_correct'].notna()]
    if known_status.empty:return None
    total = len(known_status)
    correct = known_status['is_correct'].sum()

    return (correct/total)*100


def completed_quiz_count(answers:pd.DataFrame) -> int:
    """Distinct completed attempts, practice + assessments (both count toward badges)."""
    completed = answers[answers['attempt_status']=='completed']
    return completed['attempt_id'].nunique()


# --- Stage 0 implementation ---------------------------------------------------
def evaluated_answers(answers: pd.DataFrame) -> pd.DataFrame:
    """The rows every accuracy figure is computed from (same rule as overall_accuracy)."""
    mask = (answers["attempt_status"] == "completed") & answers["is_correct"].notna()
    return answers[mask]


def _add_accuracy(table: pd.DataFrame) -> pd.DataFrame:
    table["correct"] = table["correct"].astype(int)
    table["accuracy_pct"] = table["correct"] / table["questions"] * 100
    return table


def accuracy_table(answers: pd.DataFrame, by) -> pd.DataFrame:
    """Accuracy broken down by one or more columns (subject, topic, difficulty, ...).

    Returns one row per group with:
      quizzes       distinct completed attempts that touched the group
      questions     evaluated answers (the denominator)
      correct       correct answers
      accuracy_pct  correct / questions * 100   (pooled within the group)
      avg_time_sec  mean seconds per question (NaN where time isn't recorded)
      last_attempt  latest attempt timestamp
    Rows whose group value is missing are labelled "Unmapped" rather than
    silently dropped, so group totals still add up to overall_accuracy's denominator.
    """
    by = [by] if isinstance(by, str) else list(by)
    columns = by + ["quizzes", "questions", "correct", "accuracy_pct", "avg_time_sec", "last_attempt"]
    rows = evaluated_answers(answers)
    if rows.empty:
        return pd.DataFrame(columns=columns)
    rows = rows.assign(**{c: rows[c].astype("object").where(rows[c].notna(), "Unmapped") for c in by})
    table = (
        rows.groupby(by)
        .agg(
            quizzes=("attempt_id", "nunique"),
            questions=("is_correct", "size"),
            correct=("is_correct", "sum"),
            avg_time_sec=("time_taken_sec", "mean"),
            last_attempt=("attempted_at", "max"),
        )
        .reset_index()
    )
    return _add_accuracy(table)[columns]


def progress_over_time(answers: pd.DataFrame, freq: str = "W") -> pd.DataFrame:
    """Pooled accuracy per calendar week ("W", Monday start), month ("M") or year ("Y").

    Periods use the student's local timezone and are sorted oldest -> newest.
    Periods with no evaluated answers are omitted (no fake 0% points).
    """
    rows = evaluated_answers(answers)
    columns = ["period_start", "quizzes", "questions", "correct", "accuracy_pct"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    pandas_freq = {"W": "W-SUN", "M": "M", "Y": "Y"}[freq]
    local = rows["attempted_at"].dt.tz_convert(LOCAL_TIMEZONE).dt.tz_localize(None)
    period_start = local.dt.to_period(pandas_freq).dt.start_time
    table = (
        rows.assign(period_start=period_start)
        .groupby("period_start")
        .agg(quizzes=("attempt_id", "nunique"), questions=("is_correct", "size"),
             correct=("is_correct", "sum"))
        .reset_index()
        .sort_values("period_start")
    )
    return _add_accuracy(table)[columns].reset_index(drop=True)


def _first_known(values: pd.Series):
    known = values.dropna()
    return known.iloc[0] if len(known) else None


def attempt_history(answers: pd.DataFrame) -> pd.DataFrame:
    """One row per completed attempt, oldest first: when, source, topic, accuracy."""
    rows = evaluated_answers(answers)
    columns = ["attempt_id", "attempted_at", "source", "topic", "questions", "correct", "accuracy_pct"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    table = (
        rows.groupby("attempt_id")
        .agg(attempted_at=("attempted_at", "first"), source=("source", "first"),
             topic=("topic", _first_known), questions=("is_correct", "size"),
             correct=("is_correct", "sum"))
        .reset_index()
        .sort_values("attempted_at")
    )
    return _add_accuracy(table)[columns].reset_index(drop=True)


RESPONSE_TIME_BINS = [0, 30, 60, 120, float("inf")]
RESPONSE_TIME_LABELS = ["< 30 s", "30–60 s", "1–2 min", "> 2 min"]


def response_time_vs_accuracy(answers: pd.DataFrame) -> pd.DataFrame:
    """Accuracy per response-time band, for answers where time was recorded.

    Only assessments record per-question time, so practice answers drop out.
    Blank answers are excluded here: their time reflects skipping, not solving.
    """
    rows = evaluated_answers(answers)
    rows = rows[rows["time_taken_sec"].notna() & rows["answered"].fillna(True).astype(bool)]
    columns = ["time_band", "questions", "correct", "accuracy_pct"]
    if rows.empty:
        return pd.DataFrame(columns=columns)
    band = pd.cut(rows["time_taken_sec"], RESPONSE_TIME_BINS, labels=RESPONSE_TIME_LABELS, right=False)
    table = (
        rows.assign(time_band=band)
        .groupby("time_band", observed=True)
        .agg(questions=("is_correct", "size"), correct=("is_correct", "sum"))
        .reset_index()
    )
    table["time_band"] = table["time_band"].astype(str)
    return _add_accuracy(table)[columns]


def badge_status(quiz_count: int) -> dict:
    """Current badge, next badge and quizzes still needed (architecture thresholds)."""
    current, upcoming = None, None
    for name, threshold in BADGES:
        if quiz_count >= threshold:
            current = name
        elif upcoming is None:
            upcoming = (name, threshold)
    return {
        "current": current,
        "next": upcoming[0] if upcoming else None,
        "remaining": upcoming[1] - quiz_count if upcoming else 0,
    }
