"""Smoke test: the app renders every page on the synthetic data without errors."""
import os

import pytest
from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")

# st.navigation can't be switched from AppTest, so a tiny harness runs one page function.
HARNESS = """
import streamlit as st
PAGE = {page!r}
def _nav(pages, **kwargs):
    class _Picked:
        def run(self):
            [p for p in pages if p.title == PAGE][0]._page()
    return _Picked()
st.navigation = _nav
exec(open({app!r}, encoding="utf-8").read())
"""


@pytest.mark.parametrize("page", ["Student Overview", "Quiz Analysis", "Metric definitions"])
def test_page_renders_without_errors(page, monkeypatch):
    monkeypatch.delenv("CURIO_DATA_DIR", raising=False)
    at = AppTest.from_string(HARNESS.format(page=page, app=os.path.abspath(APP)), default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]


def test_overview_kpis_show_numbers():
    at = AppTest.from_string(HARNESS.format(page="Student Overview", app=os.path.abspath(APP)),
                             default_timeout=60).run()
    values = {m.label: m.value for m in at.metric}
    assert values["Overall accuracy"] == "60.3%"
    assert values["Completed quizzes"] == "28"
    assert "Pending" not in values.values()
