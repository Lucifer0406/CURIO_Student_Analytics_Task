"""Central place for paths, thresholds and business rules.

Every number here is either (a) stated in the manager's architecture / by the
manager, or (b) a prototype default. Each constant says which one it is, so
the README and the demo can be honest about where a rule came from.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYNTHETIC_DIR = ROOT / "data" / "synthetic"

# Real export lives OUTSIDE the repo and is only used locally.
# Set it with:  export CURIO_DATA_DIR=/path/to/analytics_data_export
REAL_DATA_DIR = os.environ.get("CURIO_DATA_DIR")

# Day boundaries for streaks / daily activity. Timestamps in the export are UTC
# ("...Z"). PROTOTYPE ASSUMPTION: students are in India.
LOCAL_TIMEZONE = "Asia/Kolkata"

# --- Rules from the architecture diagram -----------------------------------
PASS_THRESHOLD_PCT = 70  # diagram: "Pass Threshold (70%)"

BADGES = [  # diagram: Achievement Badge Engine (min completed quizzes)
    ("Bronze Scholar", 5),
    ("Silver Achiever", 15),
    ("Gold Legend", 30),
]

MASTERY_LEVELS = {"Mastered": 3, "Exploring": 2, "Unexplored": 1}  # diagram

# --- Rule from the manager (2026-10-10) -------------------------------------
# mastery = 0.60*accuracy + 0.25*difficulty + 0.15*recency
# How each component is scaled to 0-1 was NOT specified -> prototype choices below.
MASTERY_WEIGHTS = {"accuracy": 0.60, "difficulty": 0.25, "recency": 0.15}

# --- Canonical vocabularies (used by preprocessing) -------------------------
SUBJECTS = ["Biology", "Chemistry", "Physics", "Mathematics"]
DIFFICULTIES = ["easy", "medium", "hard"]

# --- Mastery: PROTOTYPE interpretation of the manager's formula -------------
# The manager gave the weights only. These choices fill the gaps and are
# documented in the README as prototype rules, not company definitions.
# accuracy   = correct / evaluated questions on the topic            (0-1)
# difficulty = sum(weight of each CORRECT answer) / evaluated questions (0-1)
#              -> only correct answers on harder questions raise it, so a
#                 student who gets every hard question wrong scores 0 here.
# recency    = 0.5 ** (days since last attempt / half-life)          (0-1)
DIFFICULTY_WEIGHT = {"easy": 1 / 3, "medium": 2 / 3, "hard": 1.0}
DEFAULT_DIFFICULTY_WEIGHT = 2 / 3      # questions with unknown difficulty -> medium
RECENCY_HALF_LIFE_DAYS = 21            # recency halves every 3 weeks
MASTERED_MIN_SCORE = 70                # reuses the diagram's 70% pass threshold
MIN_EVIDENCE_QUESTIONS = 5             # fewer -> "limited evidence", never Mastered

# --- Recommendation rule thresholds (PROTOTYPE) ------------------------------
WEAK_ACCURACY_PCT = 50                 # below -> "Revise"
STRONG_ACCURACY_PCT = 80               # above (with few hard Qs) -> "Increase difficulty"
LOW_HARD_SHARE_PCT = 20
TREND_WINDOW_DAYS = 30                 # "recent" = last 30 days before the as-of date
MIN_TREND_QUESTIONS = 4                # per window, to compare recent vs earlier
DECLINE_POINTS = 20                    # recent accuracy this many points lower -> "Revisit"
STALE_DAYS = 30                        # Mastered but untouched this long -> "Quick review"
INACTIVE_DAYS = 7                      # no study this long -> "Resume regular study"
