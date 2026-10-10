import math

import pytest

from src.formatting import format_duration, format_pct


@pytest.mark.parametrize("seconds, text", [
    (0, "0m"), (29, "0m"), (30, "1m"), (2700, "45m"), (3600, "1h 0m"), (5430, "1h 31m"),
    (142_998, "39h 43m"), (None, "—"), (math.nan, "—"),
])
def test_format_duration(seconds, text):
    assert format_duration(seconds) == text


def test_format_pct():
    assert format_pct(60.2739) == "60.3%"
    assert format_pct(54.4, 0) == "54%"
    assert format_pct(None) == "—"
