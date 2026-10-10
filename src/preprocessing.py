"""Cleaning helpers shared by the real-data loader and the dashboard.

Corresponds to the architecture's "Subject Normalization" and the frontend
transformer's "Value Clamping". Pure functions: value in -> value out.
"""
import re

import pandas as pd

from src.config import DIFFICULTIES

# Keyword -> canonical subject. Checked in order; first match wins.
# Built from the subject labels that actually occur in assessments.json
# (e.g. "12th Physics", "physics", "11 th phy", "chem", "12th maths").
_SUBJECT_KEYWORDS = [
    ("Mathematics", ("math", "binomial", "bionomial", "matrices")),
    ("Chemistry", ("chem",)),
    ("Physics", ("phy", "motion")),
    ("Biology", ("bio",)),
]


def normalize_subject(label):
    """Map a messy subject label to a canonical subject, or None if unknown.

    "12th Physics" -> "Physics", "chem" -> "Chemistry",
    "qwert" / "" / None -> None (treated as unmapped, not guessed).
    """
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    text = re.sub(r"\s+", " ", str(label)).strip().lower()
    if not text or text in {"undefined", "null", "none", "unmapped", "general"}:
        return None
    for subject, keywords in _SUBJECT_KEYWORDS:
        if any(k in text for k in keywords):
            return subject
    return None


def normalize_difficulty(label):
    """'Medium' / ' HARD ' -> 'medium' / 'hard'; anything else -> None."""
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    text = str(label).strip().lower()
    return text if text in DIFFICULTIES else None


def clamp_pct(values):
    """Clip a number or Series of percentages into [0, 100] (NaN stays NaN)."""
    if isinstance(values, pd.Series):
        return values.clip(lower=0, upper=100)
    if values is None or pd.isna(values):
        return values
    return min(max(values, 0), 100)
