"""Curio Student Analytics - Streamlit entry point. UI only: every number comes from src/.

Run:                     streamlit run app.py
With real data (local):  CURIO_DATA_DIR=/path/to/analytics_data_export streamlit run app.py
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

from src import charts, learning, performance
from src.config import (
    BADGES, MASTERED_MIN_SCORE, MASTERY_WEIGHTS, MIN_EVIDENCE_QUESTIONS, PASS_THRESHOLD_PCT,
    RECENCY_HALF_LIFE_DAYS, TREND_WINDOW_DAYS,
)
from src.data_loader import load_real, load_synthetic, real_data_available
from src.formatting import format_duration, format_pct
from src.mastery import topic_mastery
from src.recommendations import recommend

st.set_page_config(page_title="Curio Student Analytics", page_icon="📊", layout="wide")

st.markdown("""
<style>
  /* "tokyo neon" tokens - page #271e33, card #2e2638, teal #7db2c0, rose #ae415e, periwinkle #596eb1, indigo #445080 */
  :root { --card:#2e2638; --border:#443b51; --ink-2:#bab4c5; --muted:#90889c;
          --teal:#7db2c0; --rose:#ce5976; --peri:#596eb1; --indigo:#445080; }
  .block-container {padding-top: 2rem; max-width: 1280px;}
  h1 {letter-spacing: -0.02em;}
  h1::after {content:""; display:block; width:56px; height:3px; margin-top:10px; border-radius:2px;
             background: linear-gradient(90deg, var(--teal), var(--peri));}

  /* cards: bordered containers and KPI tiles share one surface */
  [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {background: var(--card);}
  [data-testid="stMetric"] {background: var(--card); border-top: 3px solid var(--indigo) !important;}
  [data-testid="stMetricValue"] {font-size: 1.9rem; color: #ede9f2;}
  [data-testid="stMetricLabel"] p {font-size: 0.85rem; color: var(--ink-2);}
  [data-testid="stSidebar"] h3 {color: var(--teal);}

  .badge {display:inline-block; padding:2px 12px; border-radius:999px; font-size:0.8rem; font-weight:600;
          background: rgba(89,110,177,0.18); color:#b9c4ec; border:1px solid var(--peri);}
  .rec-reason {color: var(--ink-2); font-size:0.88rem; margin-top:-0.4rem; margin-bottom:0.9rem;}
  .muted {color: var(--muted); font-size:0.85rem;}
  .prio {font-size:0.72rem; font-weight:600; padding:1px 8px; border-radius:999px; margin-left:6px;
         text-transform:uppercase; letter-spacing:0.04em;}
  .prio-1 {color:#f3b3c4; background:rgba(206,89,118,0.18); border:1px solid var(--rose);}
  .prio-2 {color:#b9c4ec; background:rgba(89,110,177,0.18); border:1px solid var(--peri);}
  .prio-3 {color:var(--ink-2); background:rgba(68,80,128,0.25); border:1px solid var(--indigo);}
</style>
""", unsafe_allow_html=True)

PRIORITY_LABEL = {1: "High", 2: "Medium", 3: "Low"}
PLOTLY_CONFIG = {"displayModeBar": False}


@st.cache_data(show_spinner="Loading data…")
def get_dataset(source: str):
    return load_real() if source == "real" else load_synthetic()


# ============================================================== shared state ==
with st.sidebar:
    st.markdown("### Curio Analytics")
    sources = {"Synthetic demo": "synthetic"}
    if real_data_available():
        sources["Real export (local only)"] = "real"
    source = sources[st.radio("Data source", list(sources), help="Real data only appears when "
                              "CURIO_DATA_DIR is set on this machine. It is never deployed.")]
    ds = get_dataset(source)
    student = st.selectbox("Student", ds.students())

all_answers = ds.answers[ds.answers["student_id"] == student]
all_sessions = ds.sessions[ds.sessions["student_id"] == student]
timestamps = pd.concat([all_answers["attempted_at"], all_sessions["start"]]).dropna()
if timestamps.empty:
    st.warning("This student has no recorded activity.")
    st.stop()
first, last = learning.local_dates(timestamps).min(), learning.local_dates(timestamps).max()

with st.sidebar:
    picked = st.date_input("Date range", (first, last), min_value=first, max_value=last,
                           help="All metrics, charts and recommendations use only this period.")
    start, end = (picked if isinstance(picked, tuple) and len(picked) == 2 else (first, last))
    st.caption(f"Data available {first:%d %b %Y} – {last:%d %b %Y}. Dates use India time (IST).")
    if source == "synthetic":
        st.info("Synthetic student generated for this demo. No real student data is shown.", icon="ℹ️")

answers = all_answers[learning.local_dates(all_answers["attempted_at"]).between(start, end)]
sessions = all_sessions[learning.local_dates(all_sessions["start"]).between(start, end)]
as_of = end
daily = learning.daily_activity(sessions, answers, start, end)
topics = topic_mastery(answers, ds.curriculum, as_of)
recs = recommend(topics, learning.days_since_last_activity(daily, as_of))


# =================================================================== helpers ==
def chart_card(title: str, fig_builder, table: pd.DataFrame, empty_text: str, caption: str | None = None):
    """Bordered card: title, chart (or empty state), optional caption, table view."""
    with st.container(border=True):
        st.markdown(f"**{title}**")
        if table is None or table.empty:
            st.info(empty_text)
            return
        st.plotly_chart(fig_builder(table), config=PLOTLY_CONFIG, width="stretch")
        if caption:
            st.caption(caption)
        with st.expander("Table view"):
            st.dataframe(table, hide_index=True, width="stretch")


def kpi(column, label: str, value: str, help_text: str):
    column.metric(label, value, help=help_text, border=True)


def show_recommendations(table: pd.DataFrame, limit: int | None = None):
    if table.empty:
        st.success("No recommendations - nothing in this period triggers a rule.")
        return
    for rec in table.head(limit).itertuples():
        st.markdown(f"**{rec.action}**<span class='prio prio-{rec.priority}'>{PRIORITY_LABEL[rec.priority]}</span>",
                    unsafe_allow_html=True)
        st.markdown(f"<div class='rec-reason'>{rec.reason}</div>", unsafe_allow_html=True)


def topic_list(table: pd.DataFrame, ascending: bool, n: int = 3):
    attempted = table[table["questions"] >= MIN_EVIDENCE_QUESTIONS]
    if attempted.empty:
        st.caption(f"No topic has {MIN_EVIDENCE_QUESTIONS}+ answered questions yet.")
        return
    for t in attempted.sort_values("accuracy_pct", ascending=ascending).head(n).itertuples():
        st.markdown(f"**{t.topic}** <span class='muted'>· {t.subject}</span><br>"
                    f"{format_pct(t.accuracy_pct, 0)} · {t.correct}/{t.questions} correct",
                    unsafe_allow_html=True)


# ================================================================== overview ==
def overview():
    st.title("Student Overview")
    st.caption(f"{ds.label} · `{student}` · {start:%d %b %Y} – {end:%d %b %Y}")

    accuracy = performance.overall_accuracy(answers)
    quizzes = performance.completed_quiz_count(answers)
    badge = performance.badge_status(quizzes)
    streak = learning.current_streak(daily, as_of)
    consistency = learning.consistency_score(daily)

    c = st.columns(5)
    kpi(c[0], "Overall accuracy", format_pct(accuracy),
        "Correct ÷ evaluated answers, pooled over all completed quizzes and assessments. "
        "Blank answers count as wrong; answers not yet graded are excluded.")
    kpi(c[1], "Completed quizzes", f"{quizzes}",
        "Distinct finished attempts - practice quizzes and faculty assessments. "
        "Abandoned attempts are not counted.")
    kpi(c[2], "Learning time", format_duration(learning.total_learning_time(sessions)),
        "Sum of recorded session durations (learning sessions + study tools), pauses excluded.")
    kpi(c[3], "Study streak", f"{streak} day{'s' if streak != 1 else ''}",
        f"Consecutive active days ending {as_of:%d %b}. If that day has no activity yet, the streak "
        f"runs to the day before. Longest in this period: {learning.longest_streak(daily)} days.")
    kpi(c[4], "Consistency", format_pct(consistency, 0),
        "Share of days in the selected period with any study session or completed quiz.")

    badge_text = badge["current"] or "No badge yet"
    progress = f" · {badge['remaining']} more quiz{'zes' if badge['remaining'] != 1 else ''} to " \
               f"{badge['next']}" if badge["next"] else " · highest badge reached"
    st.markdown(f"<span class='badge'>{badge_text}</span> <span class='muted'>{progress}</span>",
                unsafe_allow_html=True)
    st.write("")

    left, right = st.columns([3, 2])
    with left, st.container(border=True):
        title, control = st.columns([2, 3])
        with control:
            freq_label = st.segmented_control("Group by", ["Weekly", "Monthly", "Yearly"], default="Weekly",
                                              key="freq", label_visibility="collapsed") or "Weekly"
        title.markdown(f"**{freq_label} accuracy**")
        progress_table = performance.progress_over_time(answers, {"Weekly": "W", "Monthly": "M", "Yearly": "Y"}[freq_label])
        if progress_table.empty:
            st.info("No completed quizzes in this period.")
        else:
            st.plotly_chart(charts.accuracy_trend(progress_table, freq_label.removesuffix("ly")),
                            config=PLOTLY_CONFIG, width="stretch")
            st.caption("Periods without quizzes are left out rather than shown as 0%. Hover a point for its sample size.")
            with st.expander("Table view"):
                st.dataframe(progress_table, hide_index=True, width="stretch")
    with right:
        subjects = performance.accuracy_table(answers, "subject")
        chart_card("Accuracy by subject", charts.subject_accuracy, subjects, "No graded answers in this period.",
                   "Subject labels are normalised (e.g. '12th Physics', 'phy' → Physics).")

    left, right = st.columns([3, 2])
    with left:
        change = learning.activity_change(daily, as_of)
        delta = change["change_minutes"]
        chart_card("Daily study time", charts.daily_minutes, daily if daily["minutes"].sum() > 0 else None,
                   "No study sessions in this period.",
                   f"Last 7 days: {format_duration(change['recent_minutes'] * 60)} "
                   f"({'+' if delta >= 0 else '−'}{format_duration(abs(delta) * 60)} vs the 7 days before).")
    with right:
        chart_card("Study time by subject", charts.time_by_subject, learning.time_by_subject(sessions, ds.curriculum),
                   "No study sessions in this period.",
                   "Sessions are matched to subjects through their topic.")

    left, middle, right = st.columns([1, 1, 2])
    with left, st.container(border=True):
        st.markdown("**Strongest topics**")
        topic_list(topics, ascending=False)
    with middle, st.container(border=True):
        st.markdown("**Weakest topics**")
        topic_list(topics, ascending=True)
    with right, st.container(border=True):
        st.markdown("**Recommended focus**")
        show_recommendations(recs, limit=4)
        st.caption("Rule-based and computed from the numbers on this page. Full list on Quiz Analysis.")

    left, right = st.columns(2)
    with left, st.container(border=True):
        st.markdown("**Study habits** <span class='muted'>· computed from sessions</span>", unsafe_allow_html=True)
        habits = learning.study_habits(sessions, daily)
        if habits is None:
            st.info("No study sessions in this period.")
        else:
            h1, h2 = st.columns(2)
            h1.metric("Avg session", f"{habits['avg_session_min']:.0f} min")
            h2.metric("Sessions per active day", f"{habits['sessions_per_active_day']:.1f}")
            st.markdown(
                f"- Most study happens in the **{habits['peak_daypart']}** "
                f"({habits['peak_daypart_share']:.0f}% of minutes).\n"
                f"- **{habits['weekend_share_pct']:.0f}%** of study time is on weekends.\n"
                f"- Longest streak in this period: **{learning.longest_streak(daily)} days**; "
                f"{int(daily['active'].sum())} active days out of {len(daily)}.")
            with st.expander("Session length distribution"):
                st.plotly_chart(charts.session_lengths(sessions), config=PLOTLY_CONFIG, width="stretch")
    with right, st.container(border=True):
        insight = ds.insights.get(student)
        st.markdown("**AI diagnostic report** <span class='muted'>· stored, not computed here</span>",
                    unsafe_allow_html=True)
        if not insight:
            st.info("No stored AI diagnostic for this student.")
        else:
            st.caption(f"Generated {pd.Timestamp(insight['generated_at']):%d %b %Y}. "
                       + insight.get("_note", "Text produced by the platform's AI analysis; shown as stored."))
            st.markdown(f"_{insight.get('overallSummary', '')}_")
            tabs = st.tabs(["Strengths", "Weak areas", "Behaviour", "Risks", "Action plan"])
            for tab, key in zip(tabs, ["strengths", "weakAreas", "behaviorPatterns", "riskIndicators", "actionPlan"]):
                items = insight.get(key) or []
                tab.markdown("\n".join(f"- {item}" for item in items) or "_None recorded._")


# ============================================================= quiz analysis ==
def quiz_analysis():
    st.title("Quiz Analysis")
    st.caption(f"{ds.label} · `{student}` · {start:%d %b %Y} – {end:%d %b %Y}")

    graded = performance.evaluated_answers(answers)
    f1, f2, f3 = st.columns(3)
    subject_options = sorted(graded["subject"].fillna("Unmapped").unique())
    chosen_subjects = f1.multiselect("Subject", subject_options, placeholder="All subjects")
    chosen_difficulty = f2.multiselect("Difficulty", ["easy", "medium", "hard"], placeholder="All difficulties",
                                       format_func=str.capitalize)
    chosen_source = f3.multiselect("Quiz type", ["practice", "assessment"], placeholder="Practice + assessments",
                                   format_func=lambda s: charts.SOURCE_LABELS[s])

    filtered = answers
    if chosen_subjects:
        filtered = filtered[filtered["subject"].fillna("Unmapped").isin(chosen_subjects)]
    if chosen_source:
        filtered = filtered[filtered["source"].isin(chosen_source)]
    by_topic = filtered                       # mastery ignores the difficulty filter (difficulty is part of the score)
    if chosen_difficulty:
        filtered = filtered[filtered["difficulty"].isin(chosen_difficulty)]

    graded_f = performance.evaluated_answers(filtered)
    timed = graded_f["time_taken_sec"].dropna()
    c = st.columns(4)
    kpi(c[0], "Quizzes", f"{performance.completed_quiz_count(filtered)}",
        "Completed attempts containing at least one question that matches the filters.")
    kpi(c[1], "Questions answered", f"{len(graded_f)}", "Evaluated answers (the accuracy denominator).")
    kpi(c[2], "Accuracy", format_pct(performance.overall_accuracy(filtered)), "Correct ÷ evaluated answers.")
    kpi(c[3], "Avg time per question", f"{timed.mean():.0f} s" if len(timed) else "—",
        "Only faculty assessments record time per question; practice quizzes don't.")

    left, right = st.columns(2)
    with left:
        chart_card("Accuracy by difficulty", charts.difficulty_accuracy,
                   performance.accuracy_table(filtered, "difficulty"), "No graded answers match the filters.")
    with right:
        chart_card("Accuracy vs time spent per question", charts.response_time,
                   performance.response_time_vs_accuracy(filtered),
                   "No timed answers - only faculty assessments record response time.",
                   "Assessments only. Blank answers excluded (their time reflects skipping).")

    chart_card("Performance across attempts", charts.attempts_over_time, performance.attempt_history(filtered),
               "No completed attempts match the filters.",
               "Each dot is one completed attempt (accuracy on the questions that match the filters).")

    by_source = performance.accuracy_table(filtered, "source")
    if len(by_source) == 2:
        s = by_source.set_index("source")
        gap = s.loc["practice", "accuracy_pct"] - s.loc["assessment", "accuracy_pct"]
        st.caption(f"Practice accuracy {format_pct(s.loc['practice', 'accuracy_pct'])} "
                   f"({s.loc['practice', 'questions']} questions) vs faculty assessments "
                   f"{format_pct(s.loc['assessment', 'accuracy_pct'])} ({s.loc['assessment', 'questions']} questions): "
                   f"{abs(gap):.1f} points {'higher' if gap >= 0 else 'lower'} in practice.")

    topic_table = topic_mastery(by_topic, ds.curriculum, as_of)
    if chosen_subjects:
        topic_table = topic_table[topic_table["subject"].fillna("Unmapped").isin(chosen_subjects)]
    chart_card("Topic mastery", charts.topic_mastery, topic_table, "No topics for the selected subjects.",
               f"Prototype score = {MASTERY_WEIGHTS['accuracy']:.0%} accuracy + "
               f"{MASTERY_WEIGHTS['difficulty']:.0%} difficulty + {MASTERY_WEIGHTS['recency']:.0%} recency. "
               f"Mastered = score ≥ {MASTERED_MIN_SCORE} with ≥ {MIN_EVIDENCE_QUESTIONS} questions. "
               "See Metric definitions.")

    # ---- drill-down
    attempted = topic_table[topic_table["questions"] > 0]
    with st.container(border=True):
        st.markdown("**Topic drill-down**")
        if attempted.empty:
            st.info("No attempted topics match the filters.")
        else:
            pick = st.selectbox("Topic", attempted["topic"].tolist(),
                                format_func=lambda t: f"{t} ({attempted.set_index('topic').loc[t, 'subject']})")
            t = attempted.set_index("topic").loc[pick]
            d = st.columns(6)
            d[0].metric("Level", t["level"], help=f"Evidence: {t['evidence']}")
            d[1].metric("Mastery score", f"{t['mastery_score']:.0f}")
            d[2].metric("Accuracy", format_pct(t["accuracy_pct"], 0), help=f"{t['correct']} of {t['questions']} correct")
            d[3].metric("Questions", f"{t['questions']}")
            d[4].metric("Avg time", f"{t['avg_time_sec']:.0f} s" if pd.notna(t["avg_time_sec"]) else "—",
                        help="Assessment questions only.")
            trend = t["trend_pts"]
            d[5].metric(f"Last {TREND_WINDOW_DAYS} days", format_pct(t["recent_accuracy_pct"], 0),
                        delta=f"{trend:+.0f} pts vs earlier" if pd.notna(trend) else None,
                        help="Recent vs earlier accuracy; needs 4+ questions in each window.")

            history = performance.attempt_history(by_topic[by_topic["topic"] == pick])
            g1, g2 = st.columns([3, 2])
            with g1:
                st.plotly_chart(charts.topic_attempts(history), config=PLOTLY_CONFIG, width="stretch")
            with g2:
                st.markdown("**Why this score**")
                st.markdown(
                    f"- Accuracy {t['accuracy_component']:.2f} × {MASTERY_WEIGHTS['accuracy']}\n"
                    f"- Difficulty {t['difficulty_component']:.2f} × {MASTERY_WEIGHTS['difficulty']} "
                    f"<span class='muted'>(hard questions: {format_pct(t['hard_share_pct'], 0)})</span>\n"
                    f"- Recency {t['recency_component']:.2f} × {MASTERY_WEIGHTS['recency']} "
                    f"<span class='muted'>(last attempt {int(t['days_since'])} days before {as_of:%d %b})</span>",
                    unsafe_allow_html=True)
                topic_rec = recs[recs["topic"] == pick]
                st.markdown("**Recommendation**")
                show_recommendations(topic_rec)

    with st.container(border=True):
        st.markdown("**All recommendations**")
        show_recommendations(recs)


# ======================================================= metric definitions ==
def definitions():
    st.title("Metric definitions")
    st.caption("How every number on this dashboard is calculated. Prototype rules are marked as such.")
    st.markdown(f"""
| Metric | Definition | Source of the rule |
|---|---|---|
| **Overall accuracy** | correct ÷ evaluated answers, pooled across all completed attempts. Blanks = wrong; ungraded answers excluded; in-progress attempts excluded | Prototype (intern's decision) |
| **Completed quizzes** | distinct completed attempts, practice + faculty assessments | Prototype |
| **Badges** | {", ".join(f"{n} ≥ {t}" for n, t in BADGES)} completed quizzes | Architecture diagram |
| **Pass threshold** | {PASS_THRESHOLD_PCT}% | Architecture diagram |
| **Learning time** | sum of session `durationSec` (learning sessions + study tools), pauses excluded | Prototype |
| **Active day / streak** | a local (IST) day with any study session or completed quiz; streak = consecutive active days ending on the last selected date (grace: today counts from yesterday) | Prototype |
| **Consistency** | active days ÷ days in the selected period | Prototype (diagram names it without a formula) |
| **Mastery score** | 100 × ({MASTERY_WEIGHTS['accuracy']} × accuracy + {MASTERY_WEIGHTS['difficulty']} × difficulty + {MASTERY_WEIGHTS['recency']} × recency) | Weights: manager. Components: prototype |
| ↳ accuracy | correct ÷ evaluated answers on the topic | Prototype |
| ↳ difficulty | Σ weight of each *correct* answer ÷ answers (easy ⅓, medium ⅔, hard 1) - wrong hard answers earn nothing | Prototype |
| ↳ recency | 0.5 ^ (days since last attempt ÷ {RECENCY_HALF_LIFE_DAYS}) | Prototype |
| **Mastery levels** | Mastered (3): score ≥ {MASTERED_MIN_SCORE} and ≥ {MIN_EVIDENCE_QUESTIONS} questions · Exploring (2): attempted otherwise · Unexplored (1): never attempted | Labels: diagram. Cut-offs: prototype |
| **Trend** | accuracy in the last {TREND_WINDOW_DAYS} days vs before, each needing 4+ questions | Prototype |
| **Recommendations** | one rule per topic, highest priority first: declining → weak (< 50%) → below pass → limited evidence → increase difficulty → stale mastery → unexplored | Prototype |
""")
    st.markdown("""
#### Known limitations
- The mastery score summarises recorded answers. It is **not** a validated measure of what a student knows.
- Small samples are flagged (`evidence: limited`) instead of being ranked as strong or weak.
- In the real export, practice quizzes record no subject, topic, difficulty or time per question. Topic,
  difficulty and timing analysis therefore comes from faculty assessments only.
- Learning time adds study-tool sessions to learning sessions. In the real export about 16% of tool time
  overlaps a learning session, so time can be slightly overstated.
- AI diagnostic text is displayed exactly as stored by the platform; this app does not generate or verify it.
""")


pages = st.navigation([
    st.Page(overview, title="Student Overview", icon=":material/dashboard:", default=True),
    st.Page(quiz_analysis, title="Quiz Analysis", icon=":material/quiz:"),
    st.Page(definitions, title="Metric definitions", icon=":material/menu_book:"),
])
pages.run()
