import pandas as pd
import pytest

from src.preprocessing import clamp_pct, normalize_difficulty, normalize_subject


@pytest.mark.parametrize("raw, expected", [
    # Real labels seen in assessments.json
    ("12th Physics", "Physics"),
    ("physics", "Physics"),
    ("11 th phy", "Physics"),
    ("chem", "Chemistry"),
    ("11th chem", "Chemistry"),
    ("12th maths", "Mathematics"),
    ("12 th maths", "Mathematics"),
    ("bionomial jee adv", "Mathematics"),
    ("12th Biology", "Biology"),
    ("  Motion ", "Physics"),
    # Placeholders / unknowns must become None, not a guess
    ("qwert", None),
    ("general", None),
    ("undefined", None),
    ("", None),
    (None, None),
    (float("nan"), None),
])
def test_normalize_subject(raw, expected):
    assert normalize_subject(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("Medium", "medium"), (" HARD ", "hard"), ("easy", "easy"),
    ("extreme", None), (None, None),
])
def test_normalize_difficulty(raw, expected):
    assert normalize_difficulty(raw) == expected


def test_clamp_pct_scalar_and_series():
    assert clamp_pct(120) == 100
    assert clamp_pct(-5) == 0
    assert clamp_pct(55.5) == 55.5
    result = clamp_pct(pd.Series([-1, 50, 101, None]))
    assert result.iloc[:3].tolist() == [0, 50, 100]
    assert pd.isna(result.iloc[3])
