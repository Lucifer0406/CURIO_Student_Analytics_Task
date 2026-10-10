"""Topic mastery evaluation (architecture: "Topic Mastery Evaluation").

Manager's formula:  mastery = 0.60*accuracy + 0.25*difficulty + 0.15*recency
The component definitions and the category cut-offs are PROTOTYPE choices
(see config.py) - they are not a validated estimate of what a student knows,
only a transparent summary of their recorded answers.

Levels (diagram values):
  Mastered (3)   score >= MASTERED_MIN_SCORE  AND  >= MIN_EVIDENCE_QUESTIONS answered
  Exploring (2)  attempted, but not (yet) Mastered - includes weak topics and
                 topics with too little evidence; the `evidence` column tells
                 those apart
  Unexplored (1) no evaluated answers at all
"""
from datetime import date, datetime, time, timedelta

import pandas as pd

from src.config import (
    DEFAULT_DIFFICULTY_WEIGHT, DIFFICULTY_WEIGHT, LOCAL_TIMEZONE, MASTERED_MIN_SCORE,
    MASTERY_LEVELS, MASTERY_WEIGHTS, MIN_EVIDENCE_QUESTIONS, MIN_TREND_QUESTIONS,
    RECENCY_HALF_LIFE_DAYS, TREND_WINDOW_DAYS,
)
from src.performance import evaluated_answers

COLUMNS = [
    "subject", "chapter", "topic", "questions", "correct", "accuracy_pct", "hard_share_pct",
    "avg_time_sec", "last_attempt", "days_since", "accuracy_component", "difficulty_component",
    "recency_component", "mastery_score", "level", "level_value", "evidence",
    "recent_accuracy_pct", "earlier_accuracy_pct", "trend_pts",
]


def recency_component(days_since: float) -> float:
    """1.0 if attempted today, 0.5 after one half-life, -> 0 as time passes."""
    return 0.5 ** (max(days_since, 0) / RECENCY_HALF_LIFE_DAYS)


def mastery_score(accuracy: float, difficulty: float, recency: float) -> float:
    """Weighted 0-100 score from three 0-1 components (manager's weights)."""
    w = MASTERY_WEIGHTS
    return 100 * (w["accuracy"] * accuracy + w["difficulty"] * difficulty + w["recency"] * recency)


def mastery_level(score: float, questions: int) -> str:
    if questions == 0:
        return "Unexplored"
    if score >= MASTERED_MIN_SCORE and questions >= MIN_EVIDENCE_QUESTIONS:
        return "Mastered"
    return "Exploring"


def _end_of_day_utc(as_of: date) -> pd.Timestamp:
    local_end = datetime.combine(as_of + timedelta(days=1), time.min)
    return pd.Timestamp(local_end, tz=LOCAL_TIMEZONE).tz_convert("UTC")


def _trend(rows: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Recent (last TREND_WINDOW_DAYS) vs earlier accuracy per topic."""
    cutoff = _end_of_day_utc(as_of) - pd.Timedelta(days=TREND_WINDOW_DAYS)
    recent = rows["attempted_at"] >= cutoff

    def pooled(part):
        g = part.groupby("topic")["is_correct"].agg(["size", "sum"])
        return (g["sum"] / g["size"] * 100).where(g["size"] >= MIN_TREND_QUESTIONS)

    trend = pd.DataFrame({
        "recent_accuracy_pct": pooled(rows[recent]),
        "earlier_accuracy_pct": pooled(rows[~recent]),
    })
    trend["trend_pts"] = trend["recent_accuracy_pct"] - trend["earlier_accuracy_pct"]
    return trend


def topic_mastery(answers: pd.DataFrame, curriculum: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """One row per topic (curriculum topics + any other attempted topic).

    as_of is the reference date for recency and trends - the end of the
    selected date range, so the numbers don't drift while a demo is open.
    Answers after as_of are ignored.
    """
    rows = evaluated_answers(answers)
    rows = rows[rows["topic"].notna() & (rows["attempted_at"] < _end_of_day_utc(as_of))]

    if rows.empty:
        stats = pd.DataFrame(columns=["subject", "chapter", "topic", "questions", "correct",
                                      "difficulty_points", "hard", "avg_time_sec", "last_attempt"])
    else:
        weight = rows["difficulty"].map(DIFFICULTY_WEIGHT).astype(float).fillna(DEFAULT_DIFFICULTY_WEIGHT)
        correct = rows["is_correct"].astype(bool)
        rows = rows.assign(
            difficulty_points=weight.where(correct, 0.0),
            hard=(rows["difficulty"] == "hard").fillna(False).astype(int),
        )
        stats = (
            rows.groupby("topic")
            .agg(subject=("subject", "first"), chapter=("chapter", "first"),
                 questions=("is_correct", "size"), correct=("is_correct", "sum"),
                 difficulty_points=("difficulty_points", "sum"), hard=("hard", "sum"),
                 avg_time_sec=("time_taken_sec", "mean"), last_attempt=("attempted_at", "max"))
            .reset_index()
        )

    # Outer-merge with the curriculum so never-attempted topics appear (Unexplored).
    topics = pd.concat([curriculum[["subject", "chapter", "topic"]],
                        stats[["subject", "chapter", "topic"]]]).drop_duplicates("topic")
    table = topics.merge(stats.drop(columns=["subject", "chapter"]), on="topic", how="left")
    table["questions"] = table["questions"].fillna(0).astype(int)
    table["correct"] = table["correct"].fillna(0).astype(int)

    attempted = table["questions"] > 0
    q = table["questions"].where(attempted)
    table["accuracy_pct"] = table["correct"] / q * 100
    table["hard_share_pct"] = table["hard"] / q * 100
    as_of_ts = pd.Timestamp(as_of)
    last_local = pd.to_datetime(table["last_attempt"], utc=True).dt.tz_convert(LOCAL_TIMEZONE)
    table["days_since"] = (as_of_ts - last_local.dt.tz_localize(None).dt.normalize()).dt.days

    table["accuracy_component"] = table["correct"] / q
    table["difficulty_component"] = table["difficulty_points"] / q
    table["recency_component"] = table["days_since"].map(
        lambda d: recency_component(d) if pd.notna(d) else float("nan"))
    table["mastery_score"] = [
        mastery_score(a, d, r) if ok else float("nan")
        for a, d, r, ok in zip(table["accuracy_component"], table["difficulty_component"],
                               table["recency_component"], attempted)
    ]
    table["level"] = [mastery_level(s, n) for s, n in zip(table["mastery_score"], table["questions"])]
    table["level_value"] = table["level"].map(MASTERY_LEVELS)
    table["evidence"] = pd.cut(table["questions"], [-1, 0, MIN_EVIDENCE_QUESTIONS - 1, float("inf")],
                               labels=["none", "limited", "sufficient"]).astype(str)

    trend = _trend(rows, as_of) if not rows.empty else pd.DataFrame(
        columns=["recent_accuracy_pct", "earlier_accuracy_pct", "trend_pts"])
    table = table.merge(trend, left_on="topic", right_index=True, how="left")

    for column in ["recent_accuracy_pct", "earlier_accuracy_pct", "trend_pts", "avg_time_sec"]:
        # plain float (NaN), not nullable Float64 (<NA>): comparisons stay True/False
        table[column] = pd.to_numeric(table[column], errors="coerce").astype(float)
    order = {"Mastered": 0, "Exploring": 1, "Unexplored": 2}
    table = table.sort_values(["level", "mastery_score"], key=lambda s: s.map(order) if s.name == "level" else -s)
    return table[COLUMNS].reset_index(drop=True)
