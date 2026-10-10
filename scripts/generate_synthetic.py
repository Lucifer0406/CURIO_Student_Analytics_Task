"""Generate the public synthetic demo dataset in data/synthetic/.

Run:  python scripts/generate_synthetic.py

Why synthetic? The real export contains personal data and no single student
in it has quiz + topic + engagement coverage at the same time. This script
creates ONE coherent fake student whose records follow the schema contract in
src/data_loader.py, with deliberately planted patterns so every dashboard
feature has something real to detect:

  strong topic          Kingdom Protista
  consistently weak     Human Neural System, Enthalpy
  declining             Reflex Action (good early, poor recently)
  improving             Projectile Motion
  insufficient evidence Algae (one short quiz only)
  unexplored            Le Chatelier's Principle, Ohm's Law (never attempted)
  activity gap          2026-08-10 .. 2026-08-24 (no study)
  current streak        last 6 days active

Faithful to the real platform: practice quizzes have NO per-question time
(quizattempts doesn't record it); only assessments do.
Seeded -> re-running produces identical files.
"""
import json
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.config import LOCAL_TIMEZONE, SYNTHETIC_DIR  # noqa: E402

SEED = 42
STUDENT = "demo-student-001"
START, END = date(2026, 7, 1), date(2026, 10, 8)
GAP = (date(2026, 8, 10), date(2026, 8, 24))
TZ = ZoneInfo(LOCAL_TIMEZONE)

# (subject, chapter, topic, skill_at_start, skill_at_end, practice_weight)
TOPICS = [
    ("Biology", "Biological Classification", "Kingdom Protista", 0.85, 0.88, 3),
    ("Biology", "Biological Classification", "Kingdom Fungi", 0.72, 0.78, 2),
    ("Biology", "Neural Control and Coordination", "Human Neural System", 0.45, 0.42, 3),
    ("Biology", "Neural Control and Coordination", "Reflex Action", 0.85, 0.40, 2),
    ("Biology", "Plant Kingdom", "Algae", 0.60, 0.60, 0),
    ("Chemistry", "Structure of Atom", "Subatomic Particles", 0.70, 0.74, 2),
    ("Chemistry", "Structure of Atom", "Bohr's Model", 0.62, 0.66, 1),
    ("Chemistry", "Thermodynamics", "Enthalpy", 0.40, 0.46, 2),
    ("Chemistry", "Equilibrium", "Le Chatelier's Principle", 0.0, 0.0, 0),
    ("Physics", "Motion in a Plane", "Projectile Motion", 0.38, 0.86, 3),
    ("Physics", "Laws of Motion", "Newton's Second Law", 0.65, 0.68, 2),
    ("Physics", "Current Electricity", "Ohm's Law", 0.0, 0.0, 0),
    ("Physics", "Waves", "Wave Speed", 0.55, 0.57, 1),
]
LOW_EVIDENCE_TOPIC = "Algae"
DIFFICULTY_SHIFT = {"easy": 0.12, "medium": 0.0, "hard": -0.18}
BASE_SECONDS = {"easy": 35, "medium": 60, "hard": 95}
TOOLS = ["chatbot", "whiteboard", "studyBuddy", "stickyNotes"]
ASSESSMENT_DAYS = [date(2026, 7, 20), date(2026, 8, 5), date(2026, 9, 1), date(2026, 9, 25)]

rng = np.random.default_rng(SEED)
total_days = (END - START).days


def skill(topic_row, day):
    _, _, _, s0, s1, _ = topic_row
    frac = (day - START).days / total_days
    return s0 + (s1 - s0) * frac


def p_correct(topic_row, day, difficulty):
    return float(np.clip(skill(topic_row, day) + DIFFICULTY_SHIFT[difficulty], 0.05, 0.97))


def local_dt(day, hour, minute=0):
    return datetime.combine(day, time(hour, minute), tzinfo=TZ)


def iso_utc(dt):
    return dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def pick_difficulty():
    return rng.choice(["easy", "medium", "hard"], p=[0.35, 0.5, 0.15])


def active_days():
    days = []
    for i in range(total_days + 1):
        day = START + timedelta(days=i)
        if GAP[0] <= day <= GAP[1]:
            continue
        if day > END - timedelta(days=6) or rng.random() < 0.6:
            days.append(day)
    return days


def make_sessions(days):
    practiced = [t for t in TOPICS if t[5] > 0]
    weights = np.array([t[5] for t in practiced], dtype=float)
    weights /= weights.sum()
    rows, n = [], 0
    for day in days:
        cursor = local_dt(day, int(rng.integers(16, 21)), int(rng.integers(0, 60)))
        for _ in range(int(rng.integers(1, 4))):
            topic = practiced[rng.choice(len(practiced), p=weights)]
            minutes = float(np.clip(rng.lognormal(np.log(20), 0.5), 3, 75))
            end = cursor + timedelta(minutes=minutes)
            n += 1
            rows.append({"session_id": f"ls-{n:04d}", "student_id": STUDENT, "kind": "learning",
                         "activity": topic[2], "start": iso_utc(cursor), "end": iso_utc(end),
                         "duration_sec": round(minutes * 60)})
            cursor = end + timedelta(minutes=float(rng.integers(5, 40)))
        if rng.random() < 0.35:
            minutes = float(np.clip(rng.lognormal(np.log(8), 0.6), 2, 30))
            end = cursor + timedelta(minutes=minutes)
            n += 1
            rows.append({"session_id": f"ts-{n:04d}", "student_id": STUDENT, "kind": "tool",
                         "activity": str(rng.choice(TOOLS)), "start": iso_utc(cursor), "end": iso_utc(end),
                         "duration_sec": round(minutes * 60)})
    return rows


def answer_row(attempt_id, source, status, when, topic_row, difficulty, day, with_time, blank_rate):
    blank = rng.random() < blank_rate
    correct = (not blank) and rng.random() < p_correct(topic_row, day, difficulty)
    seconds = None
    if with_time:
        seconds = BASE_SECONDS[difficulty] * rng.lognormal(0, 0.35) * (1.0 if correct else 1.15)
        seconds = round(float(seconds), 1)
    return {"attempt_id": attempt_id, "student_id": STUDENT, "source": source, "attempt_status": status,
            "attempted_at": iso_utc(when), "subject": topic_row[0], "chapter": topic_row[1],
            "topic": topic_row[2], "difficulty": difficulty, "answered": not blank,
            "is_correct": correct, "time_taken_sec": seconds}


def make_practice(days):
    practiced = [t for t in TOPICS if t[5] > 0]
    weights = np.array([t[5] for t in practiced], dtype=float)
    weights /= weights.sum()
    rows, n = [], 0
    quiz_days = [d for d in days if rng.random() < 0.4]
    for day in quiz_days:
        n += 1
        topic = practiced[rng.choice(len(practiced), p=weights)]
        when = local_dt(day, 21, int(rng.integers(0, 60)))
        for _ in range(int(rng.choice([8, 10]))):
            rows.append(answer_row(f"pq-{n:03d}", "practice", "completed", when, topic,
                                   pick_difficulty(), day, with_time=False, blank_rate=0.0))
    # One short quiz on the low-evidence topic.
    n += 1
    low = next(t for t in TOPICS if t[2] == LOW_EVIDENCE_TOPIC)
    day = date(2026, 9, 12)
    for _ in range(4):
        rows.append(answer_row(f"pq-{n:03d}", "practice", "completed", local_dt(day, 20), low,
                               pick_difficulty(), day, with_time=False, blank_rate=0.0))
    # One abandoned (in-progress) attempt: must NOT count as a completed quiz.
    n += 1
    day = date(2026, 10, 7)
    topic = next(t for t in TOPICS if t[2] == "Enthalpy")
    for _ in range(3):
        rows.append(answer_row(f"pq-{n:03d}", "practice", "in_progress", local_dt(day, 22), topic,
                               pick_difficulty(), day, with_time=False, blank_rate=0.0))
    return rows


def make_assessments():
    pool = [t for t in TOPICS if t[5] > 0]
    rows = []
    for i, day in enumerate(ASSESSMENT_DAYS, start=1):
        when = local_dt(day, 11)
        for j in range(20):
            topic = pool[(j + i) % len(pool)]
            rows.append(answer_row(f"as-{i:02d}", "assessment", "completed", when, topic,
                                   pick_difficulty(), day, with_time=True, blank_rate=0.06))
    return rows


INSIGHTS = {
    STUDENT: {
        "generated_at": "2026-10-01T09:00:00.000Z",
        "_note": "SYNTHETIC SAMPLE standing in for a stored aianalysishistories record. "
                 "Not generated by Gemini and not computed by this app.",
        "overallSummary": "Steady practice in Biology with clear gaps in Neural Control and Thermodynamics.",
        "strengths": ["Biological Classification", "Recent improvement in Projectile Motion"],
        "weakAreas": ["Human Neural System", "Enthalpy"],
        "behaviorPatterns": ["Studies mostly in the evening", "Two-week break in August"],
        "riskIndicators": ["Declining results in Reflex Action"],
        "actionPlan": ["Revise Human Neural System with short daily quizzes",
                       "Re-attempt Enthalpy problems at easy difficulty first"],
    }
}


def main():
    days = active_days()
    sessions = pd.DataFrame(make_sessions(days))
    answers = pd.DataFrame(make_practice(days) + make_assessments())
    curriculum = pd.DataFrame([t[:3] for t in TOPICS], columns=["subject", "chapter", "topic"])

    SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    answers.to_csv(SYNTHETIC_DIR / "answers.csv", index=False)
    sessions.to_csv(SYNTHETIC_DIR / "sessions.csv", index=False)
    curriculum.to_csv(SYNTHETIC_DIR / "curriculum.csv", index=False)
    (SYNTHETIC_DIR / "insights.json").write_text(json.dumps(INSIGHTS, indent=2), encoding="utf-8")

    print(f"active days: {len(days)}  sessions: {len(sessions)}  answers: {len(answers)}  "
          f"attempts: {answers['attempt_id'].nunique()}")


if __name__ == "__main__":
    main()
