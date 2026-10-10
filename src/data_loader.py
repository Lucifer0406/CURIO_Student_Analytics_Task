"""Load data into ONE fixed, tidy schema - regardless of where it came from.

The calculation modules (performance.py, mastery.py, ...) only ever see the
tables below. They never know whether the data is synthetic CSV or the real
MongoDB export. That "schema contract" is what lets us develop on safe
synthetic data and still run the same code on real data locally.

answers  - one row per question answered in a quiz/assessment attempt
    attempt_id      str
    student_id      str
    source          "practice" (quizattempts) | "assessment" (assessmentattempts)
    attempt_status  "completed" | "in_progress"
    attempted_at    datetime (UTC) - when the attempt was submitted/started
    subject         str | <NA>   canonical subject (see preprocessing.py)
    chapter         str | <NA>
    topic           str | <NA>
    difficulty      "easy" | "medium" | "hard" | <NA>
    answered        bool | <NA>  False = left blank, <NA> = unknown
    is_correct      bool | <NA>  <NA> = not evaluated yet
    time_taken_sec  float | NaN

sessions - one row per learning/tool session
    session_id, student_id, kind ("learning" | "tool"), activity (topic or tool
    name), start, end (datetime UTC), duration_sec (float)

curriculum - the topics a student COULD study (needed for "Unexplored")
    subject, chapter, topic

insights - {student_id: {"generated_at": ..., "overallSummary": str,
            "strengths": [...], "weakAreas": [...], ...}}  (stored AI output)
"""
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.config import REAL_DATA_DIR, SYNTHETIC_DIR
from src.preprocessing import normalize_difficulty, normalize_subject

ANSWER_COLUMNS = [
    "attempt_id", "student_id", "source", "attempt_status", "attempted_at",
    "subject", "chapter", "topic", "difficulty", "answered", "is_correct",
    "time_taken_sec",
]
SESSION_COLUMNS = ["session_id", "student_id", "kind", "activity", "start", "end", "duration_sec"]
CURRICULUM_COLUMNS = ["subject", "chapter", "topic"]


@dataclass
class Dataset:
    answers: pd.DataFrame
    sessions: pd.DataFrame
    curriculum: pd.DataFrame
    insights: dict = field(default_factory=dict)
    label: str = ""

    def students(self):
        ids = set(self.answers["student_id"]) | set(self.sessions["student_id"])
        return sorted(ids)


def _enforce_types(answers, sessions, curriculum):
    """Give both sources identical dtypes so downstream code behaves the same."""
    answers = answers.reindex(columns=ANSWER_COLUMNS)
    answers["attempted_at"] = pd.to_datetime(answers["attempted_at"], utc=True)
    answers["answered"] = answers["answered"].astype("boolean")
    answers["is_correct"] = answers["is_correct"].astype("boolean")
    answers["time_taken_sec"] = pd.to_numeric(answers["time_taken_sec"], errors="coerce").astype(float)

    sessions = sessions.reindex(columns=SESSION_COLUMNS)
    sessions["start"] = pd.to_datetime(sessions["start"], utc=True)
    sessions["end"] = pd.to_datetime(sessions["end"], utc=True)
    sessions["duration_sec"] = pd.to_numeric(sessions["duration_sec"], errors="coerce").astype(float)

    curriculum = curriculum.reindex(columns=CURRICULUM_COLUMNS).drop_duplicates().reset_index(drop=True)
    return answers, sessions, curriculum


# --------------------------------------------------------------------------
# Synthetic (public, committed) data
# --------------------------------------------------------------------------
def load_synthetic(directory=SYNTHETIC_DIR):
    directory = Path(directory)
    answers = pd.read_csv(directory / "answers.csv")
    sessions = pd.read_csv(directory / "sessions.csv")
    curriculum = pd.read_csv(directory / "curriculum.csv")
    insights = json.loads((directory / "insights.json").read_text(encoding="utf-8"))
    answers, sessions, curriculum = _enforce_types(answers, sessions, curriculum)
    return Dataset(answers, sessions, curriculum, insights, label="Synthetic demo data")


# --------------------------------------------------------------------------
# Real MongoDB export (local only - never committed or deployed)
# --------------------------------------------------------------------------
# Deliberately NOT loaded: users.json (PII, tokens, OTPs),
# conversationhistories.json (private messages), topicinteractions.json
# (498/500 sessionIds duplicate engagementSessions -> would double-count time),
# voicesessions.json (99 of 105 userIds are not in users.json, no duration).

def _read(directory, name):
    with open(Path(directory) / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _answered_flag(answer, missing_means_blank):
    """Was the question answered? Returns True/False, or <NA> if unknowable.

    assessmentattempts: a missing userAnswer means "left blank" - verified,
    the 576 missing values equal the sum of result.unattemptedCount.
    quizattempts: older records never stored userAnswer (795 of them are
    still marked correct), so missing means "unknown", not blank.
    """
    if "userAnswer" not in answer:
        return False if missing_means_blank else pd.NA
    return bool(str(answer["userAnswer"]).strip())


def _real_practice_answers(directory):
    # quizattempts: summary fields (correctAnswers, score, totalMarks,
    # totalQuestions) contradict the answers array in most records, so we
    # rebuild everything from answers[].isCorrect. No subject/difficulty here.
    rows = []
    for attempt in _read(directory, "quizattempts"):
        status = "completed" if attempt["status"] == "completed" else "in_progress"
        for answer in attempt["answers"]:
            rows.append({
                "attempt_id": attempt["_id"],
                "student_id": attempt["userId"],
                "source": "practice",
                "attempt_status": status,
                "attempted_at": attempt.get("completedAt") or attempt["startedAt"],
                "subject": None,
                "chapter": None,
                "topic": attempt.get("topicTitle"),
                "difficulty": None,
                "answered": _answered_flag(answer, missing_means_blank=False),
                "is_correct": answer.get("isCorrect", pd.NA),
                "time_taken_sec": None,  # not recorded per question
            })
    return rows


def _real_assessment_answers(directory):
    # Each answer joins to assessments.questionSnapshots[]._id (1127/1127 in
    # the export), which carries subject/chapter/topic/difficulty.
    snapshots = {
        snap["_id"]: snap
        for assessment in _read(directory, "assessments")
        for snap in assessment["questionSnapshots"]
    }
    rows = []
    for attempt in _read(directory, "assessmentattempts"):
        status = "completed" if attempt["status"] == "SUBMITTED" else "in_progress"
        for answer in attempt["answers"]:
            snap = snapshots.get(answer["questionSnapshotId"], {})
            taxonomy = snap.get("taxonomy", {})
            evaluated = answer.get("evaluationStatus") == "AUTO_EVALUATED"
            rows.append({
                "attempt_id": attempt["_id"],
                "student_id": attempt["studentId"],
                "source": "assessment",
                "attempt_status": status,
                "attempted_at": attempt.get("submittedAt") or attempt["startedAt"],
                "subject": normalize_subject(taxonomy.get("subjectLabel")),
                "chapter": taxonomy.get("chapterLabel"),
                "topic": taxonomy.get("topicLabel"),
                "difficulty": normalize_difficulty(snap.get("difficulty")),
                "answered": _answered_flag(answer, missing_means_blank=True),
                "is_correct": answer.get("isCorrect", pd.NA) if evaluated else pd.NA,
                "time_taken_sec": answer.get("timeTakenMs", 0) / 1000,
            })
    return rows


def _real_sessions(directory):
    rows = []
    for s in _read(directory, "engagementSessions"):
        rows.append({
            "session_id": s["sessionId"], "student_id": s["userId"], "kind": "learning",
            "activity": s.get("topicTitle"), "start": s["start"], "end": s.get("end"),
            "duration_sec": s["durationSec"],
        })
    for s in _read(directory, "toolusages"):
        rows.append({
            "session_id": s["_id"], "student_id": s["userId"], "kind": "tool",
            "activity": s["toolName"], "start": s["startedAt"], "end": s.get("endedAt"),
            "duration_sec": s["durationSec"],
        })
    return pd.DataFrame(rows)


def _real_curriculum(directory):
    rows = []
    for assessment in _read(directory, "assessments"):
        for snap in assessment["questionSnapshots"]:
            taxonomy = snap.get("taxonomy", {})
            subject = normalize_subject(taxonomy.get("subjectLabel"))
            if subject and taxonomy.get("topicLabel"):
                rows.append({"subject": subject, "chapter": taxonomy.get("chapterLabel"),
                             "topic": taxonomy["topicLabel"]})
    return pd.DataFrame(rows, columns=CURRICULUM_COLUMNS)


def _real_insights(directory):
    latest = {}
    for record in _read(directory, "aianalysishistories"):
        uid = record["userId"]
        if uid not in latest or record["generatedAt"] > latest[uid]["generated_at"]:
            insight = {k: v for k, v in record["insights"].items() if k != "_id"}
            latest[uid] = {"generated_at": record["generatedAt"], **insight}
    return latest


def load_real(directory=REAL_DATA_DIR):
    if not directory or not Path(directory).is_dir():
        raise FileNotFoundError(
            "Real data directory not found. Set CURIO_DATA_DIR to the extracted export folder."
        )
    answers = pd.DataFrame(_real_practice_answers(directory) + _real_assessment_answers(directory))
    answers, sessions, curriculum = _enforce_types(answers, _real_sessions(directory), _real_curriculum(directory))
    return Dataset(answers, sessions, curriculum, _real_insights(directory), label="Real export (local only)")


def real_data_available():
    return bool(REAL_DATA_DIR) and Path(REAL_DATA_DIR).is_dir()
