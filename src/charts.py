"""Plotly figure builders. Each takes a tidy table from src/ and returns a Figure.

Visual rules (from the data-viz guidelines this project follows):
  * one series -> one colour (teal); colour follows the entity, never the rank
  * practice vs assessment always teal / rose (validated colour-blind-safe pair)
  * mastery levels: teal / periwinkle / neutral grey, always with a text label
  * thin bars with rounded data-ends, 2px lines, hairline grid, one y-axis only
  * every chart has hover details; the app adds a table view underneath
"""
import pandas as pd
import plotly.graph_objects as go

from src.config import PASS_THRESHOLD_PCT

# Chart-safe steps of the "tokyo neon" hues (validated: colour-blind separation and
# contrast on the dark card surface). The raw swatches are too pale/dark for data marks.
TEAL = "#10a3bf"         # primary series, Mastered
ROSE = "#ce5976"         # second series (assessments), thresholds
PERIWINKLE = "#465dad"   # Exploring (always shown with a score label + legend)
NEUTRAL = "#65616d"      # Unexplored = "no data", deliberately not a hue

SOURCE_COLORS = {"practice": TEAL, "assessment": ROSE}
SOURCE_LABELS = {"practice": "Practice quiz", "assessment": "Faculty assessment"}
LEVEL_COLORS = {"Mastered": TEAL, "Exploring": PERIWINKLE, "Unexplored": NEUTRAL}

SURFACE = "#2e2638"                       # card colour behind every chart
INK, INK_2, MUTED = "#ede9f2", "#bab4c5", "#90889c"
GRID, AXIS = "#3a3147", "#443b51"
FONT = 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif'
DIFFICULTY_ORDER = ["easy", "medium", "hard", "Unmapped"]


def _style(fig: go.Figure, height: int = 300, y_title: str = "", x_title: str = "") -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=8, r=16, t=16, b=8),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=INK_2),
        hoverlabel=dict(bgcolor="#1c1625", bordercolor=AXIS, font=dict(family=FONT, color=INK)),
        bargap=0.45, barcornerradius=4, showlegend=False,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
    )
    fig.update_xaxes(title=x_title, showgrid=False, linecolor=AXIS, tickfont=dict(color=MUTED), zeroline=False)
    fig.update_yaxes(title=y_title, gridcolor=GRID, gridwidth=1, linecolor=AXIS,
                     tickfont=dict(color=MUTED), zeroline=False)
    return fig


def _pass_line(fig: go.Figure, horizontal: bool = True) -> None:
    kwargs = dict(line=dict(color=MUTED, width=1), opacity=0.9)
    label = f"Pass {PASS_THRESHOLD_PCT}%"
    if horizontal:
        fig.add_hline(y=PASS_THRESHOLD_PCT, annotation_text=label, annotation_position="top right",
                      annotation_font=dict(color=MUTED, size=11), **kwargs)
    else:
        fig.add_vline(x=PASS_THRESHOLD_PCT, annotation_text=label, annotation_position="top",
                      annotation_font=dict(color=MUTED, size=11), **kwargs)


def accuracy_trend(progress: pd.DataFrame, period_label: str) -> go.Figure:
    """Pooled accuracy per period (single series) with the pass threshold."""
    fig = go.Figure(go.Scatter(
        x=progress["period_start"], y=progress["accuracy_pct"], mode="lines+markers",
        line=dict(color=TEAL, width=2), marker=dict(size=8, color=TEAL, line=dict(color=SURFACE, width=2)),
        customdata=progress[["questions", "correct", "quizzes"]],
        hovertemplate=f"<b>{period_label} of %{{x|%d %b %Y}}</b><br>Accuracy %{{y:.1f}}%"
                      "<br>%{customdata[1]} of %{customdata[0]} correct · %{customdata[2]} quizzes<extra></extra>",
    ))
    _pass_line(fig)
    fig.update_yaxes(range=[0, 105], ticksuffix="%")
    return _style(fig, y_title="Accuracy")


def horizontal_bars(table: pd.DataFrame, label: str, value: str, hover: str,
                    suffix: str = "", pass_line: bool = False, height: int | None = None) -> go.Figure:
    """Single-series horizontal bars, largest at the top. `hover` is a hovertemplate tail."""
    table = table.sort_values(value)
    fig = go.Figure(go.Bar(
        x=table[value], y=table[label], orientation="h", marker_color=TEAL,
        text=[f"{v:.0f}{suffix}" for v in table[value]], textposition="outside",
        textfont=dict(color=INK_2), cliponaxis=False,
        customdata=table.drop(columns=[label]).to_numpy(), hovertemplate=hover + "<extra></extra>",
    ))
    if pass_line:
        _pass_line(fig, horizontal=False)
        fig.update_xaxes(range=[0, 112], ticksuffix="%")
    fig.update_xaxes(showgrid=True, gridcolor=GRID)
    fig.update_yaxes(showgrid=False)
    return _style(fig, height=height or max(180, 48 * len(table) + 60))


def subject_accuracy(table: pd.DataFrame) -> go.Figure:
    t = table[["subject", "accuracy_pct", "questions", "correct", "avg_time_sec"]]
    return horizontal_bars(
        t, "subject", "accuracy_pct", suffix="%", pass_line=True,
        hover="<b>%{y}</b><br>Accuracy %{x:.1f}%<br>%{customdata[2]} of %{customdata[1]} correct",
    )


def time_by_subject(table: pd.DataFrame) -> go.Figure:
    t = table[["subject", "minutes", "sessions"]].assign(hours=table["minutes"] / 60)[["subject", "hours", "sessions"]]
    return horizontal_bars(t, "subject", "hours", suffix="h",
                           hover="<b>%{y}</b><br>%{x:.1f} hours · %{customdata[1]} sessions")


def daily_minutes(daily: pd.DataFrame) -> go.Figure:
    fig = go.Figure(go.Bar(
        x=pd.to_datetime(daily["date"]), y=daily["minutes"], marker_color=TEAL,
        customdata=daily[["sessions", "quizzes"]],
        hovertemplate="<b>%{x|%a %d %b}</b><br>%{y:.0f} min studied"
                      "<br>%{customdata[0]} sessions · %{customdata[1]} quizzes<extra></extra>",
    ))
    fig.update_layout(bargap=0.25)
    return _style(fig, height=260, y_title="Minutes")


def difficulty_accuracy(table: pd.DataFrame) -> go.Figure:
    order = [d for d in DIFFICULTY_ORDER if d in set(table["difficulty"])]
    t = table.set_index("difficulty").loc[order].reset_index()
    fig = go.Figure(go.Bar(
        x=t["difficulty"].str.capitalize(), y=t["accuracy_pct"], marker_color=TEAL,
        text=[f"{v:.0f}%" for v in t["accuracy_pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_2),
        customdata=t[["questions", "correct", "avg_time_sec"]],
        hovertemplate="<b>%{x}</b><br>Accuracy %{y:.1f}%<br>%{customdata[1]} of %{customdata[0]} correct"
                      "<br>Avg time %{customdata[2]:.0f} s<extra></extra>",
    ))
    _pass_line(fig)
    fig.update_yaxes(range=[0, 112], ticksuffix="%")
    return _style(fig, height=280, y_title="Accuracy")


def attempts_over_time(history: pd.DataFrame) -> go.Figure:
    """Accuracy of each attempt, practice and assessments as two labelled series."""
    fig = go.Figure()
    for source, color in SOURCE_COLORS.items():
        part = history[history["source"] == source]
        if part.empty:
            continue
        fig.add_trace(go.Scatter(
            x=part["attempted_at"], y=part["accuracy_pct"], mode="markers", name=SOURCE_LABELS[source],
            marker=dict(size=9, color=color, line=dict(color=SURFACE, width=2)),
            customdata=part[["topic", "correct", "questions"]].fillna("—"),
            hovertemplate="<b>%{customdata[0]}</b><br>%{x|%d %b %Y}<br>%{y:.0f}% "
                          "(%{customdata[1]} of %{customdata[2]})<extra>" + SOURCE_LABELS[source] + "</extra>",
        ))
    _pass_line(fig)
    fig.update_yaxes(range=[-5, 108], ticksuffix="%")
    _style(fig, height=300, y_title="Attempt accuracy")
    fig.update_layout(showlegend=True)
    return fig


def response_time(table: pd.DataFrame) -> go.Figure:
    # Show the sample size under each band so a 5-question band isn't read as a pattern.
    labels = [f"{band}<br><span style='font-size:11px'>{n} questions</span>"
              for band, n in zip(table["time_band"], table["questions"])]
    fig = go.Figure(go.Bar(
        x=labels, y=table["accuracy_pct"], marker_color=TEAL,
        text=[f"{v:.0f}%" for v in table["accuracy_pct"]], textposition="outside", cliponaxis=False,
        textfont=dict(color=INK_2), customdata=table[["questions", "correct"]],
        hovertemplate="<b>%{x}</b><br>Accuracy %{y:.1f}%"
                      "<br>%{customdata[1]} of %{customdata[0]} correct<extra></extra>",
    ))
    fig.update_yaxes(range=[0, 112], ticksuffix="%")
    return _style(fig, height=280, y_title="Accuracy", x_title="Time spent on the question")


def topic_mastery(topics: pd.DataFrame) -> go.Figure:
    """Mastery score per topic, coloured by level (status colours + legend labels)."""
    t = topics.assign(score=topics["mastery_score"].fillna(0)).iloc[::-1]
    fig = go.Figure()
    for level, color in LEVEL_COLORS.items():
        part = t[t["level"] == level]
        if part.empty:
            continue
        text = ["Not attempted" if level == "Unexplored" else f"{s:.0f}" for s in part["score"]]
        fig.add_trace(go.Bar(
            x=part["score"] if level != "Unexplored" else [1.5] * len(part),
            y=part["topic"], orientation="h", name=level, marker_color=color,
            text=text, textposition="outside", cliponaxis=False, textfont=dict(color=INK_2),
            customdata=part[["subject", "questions", "accuracy_pct", "evidence"]].fillna("—"),
            hovertemplate="<b>%{y}</b> (%{customdata[0]})<br>" + level +
                          "<br>Score %{text}<br>%{customdata[1]} questions · evidence: %{customdata[3]}<extra></extra>",
        ))
    fig.update_layout(barmode="overlay", bargap=0.35)
    fig.update_yaxes(categoryorder="array", categoryarray=list(t["topic"]), showgrid=False)
    fig.update_xaxes(range=[0, 108], showgrid=True, gridcolor=GRID, title="Mastery score (0–100)")
    _style(fig, height=max(260, 34 * len(t) + 80))
    fig.update_layout(showlegend=True)
    return fig


def topic_attempts(history: pd.DataFrame) -> go.Figure:
    """Accuracy of each attempt on one topic, in order (single series)."""
    fig = go.Figure(go.Scatter(
        x=history["attempted_at"], y=history["accuracy_pct"], mode="lines+markers",
        line=dict(color=TEAL, width=2), marker=dict(size=8, color=TEAL, line=dict(color=SURFACE, width=2)),
        customdata=history[["correct", "questions", "source"]],
        hovertemplate="%{x|%d %b %Y}<br>%{y:.0f}% (%{customdata[0]} of %{customdata[1]})"
                      "<br>%{customdata[2]}<extra></extra>",
    ))
    _pass_line(fig)
    fig.update_yaxes(range=[-5, 108], ticksuffix="%")
    return _style(fig, height=260, y_title="Accuracy")


def session_lengths(sessions: pd.DataFrame) -> go.Figure:
    minutes = sessions.loc[sessions["duration_sec"] > 0, "duration_sec"] / 60
    fig = go.Figure(go.Histogram(
        x=minutes, xbins=dict(start=0, size=5), marker_color=TEAL,
        hovertemplate="%{x} min<br>%{y} sessions<extra></extra>",
    ))
    fig.update_layout(bargap=0.15)
    return _style(fig, height=260, y_title="Sessions", x_title="Session length (minutes)")
