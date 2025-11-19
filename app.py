# app.py — Streamlit Prototype: DADS9 - 5002 Score
# - Student can append unlimited questions before preview/submit
# - Safe Back/Next, progress clamped
# - Optional edit of question text per submission
import streamlit as st
import sqlite3
import pandas as pd
from datetime import date

DB_PATH = "answers.db"

# Local safety; on Streamlit Cloud this exists
if not st.runtime.exists():
    print("\n[!] Please run with:  streamlit run app.py\n")
    raise SystemExit


# ---------- DB Utilities ----------
def get_con():
    return sqlite3.connect(DB_PATH)


def init_db():
    con = get_con()
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date_week TEXT NOT NULL,
            question_no INTEGER NOT NULL,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            group_name TEXT,
            checked INTEGER DEFAULT 0
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date_week TEXT NOT NULL,
            question_no INTEGER NOT NULL,
            question TEXT NOT NULL,
            UNIQUE(date_week, question_no) ON CONFLICT REPLACE
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS student_logins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date_week TEXT NOT NULL,
            logged_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(student_id, date_week) ON CONFLICT IGNORE
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS class_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date_week TEXT NOT NULL,
            score REAL,
            note TEXT,
            UNIQUE(student_id, date_week) ON CONFLICT REPLACE
        );
        """
    )
    # participation table per student per date
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS participation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date_week TEXT NOT NULL,
            participation INTEGER DEFAULT 0,
            UNIQUE(student_id, date_week) ON CONFLICT REPLACE
        );
        """
    )

    # ensure group_name column exists on answers
    cur.execute("PRAGMA table_info(answers)")
    existing_cols = [row[1] for row in cur.fetchall()]
    if "group_name" not in existing_cols:
        cur.execute("ALTER TABLE answers ADD COLUMN group_name TEXT")

    # global weighting scheme (single row, id = 1)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS score_weights (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            w_answers REAL NOT NULL DEFAULT 1.0,
            w_class REAL NOT NULL DEFAULT 1.0,
            w_part REAL NOT NULL DEFAULT 1.0
        );
        """
    )

    con.commit()
    con.close()


DEFAULT_QUESTIONS = [
    "Explain one key concept you learned today.",
    "Give an example related to the concept.",
    "What is one question you still have?",
]


def load_questions(date_week: str | None):
    if not date_week:
        return DEFAULT_QUESTIONS.copy()
    con = get_con()
    df = pd.read_sql_query(
        "SELECT question_no, question FROM questions WHERE date_week=? ORDER BY question_no",
        con,
        params=[date_week],
    )
    con.close()
    if df.empty:
        return DEFAULT_QUESTIONS.copy()
    q = df.sort_values("question_no")["question"].tolist()
    return q if len(q) > 0 else DEFAULT_QUESTIONS.copy()


def save_question_set(date_week: str, questions: list[str]):
    con = get_con()
    cur = con.cursor()
    cur.execute("DELETE FROM questions WHERE date_week=?", (date_week,))
    for idx, q in enumerate([q.strip() for q in questions], start=1):
        if q:
            cur.execute(
                "INSERT INTO questions (date_week, question_no, question) VALUES (?,?,?)",
                (date_week, idx, q),
            )
    con.commit()
    con.close()


def list_question_dates():
    con = get_con()
    df = pd.read_sql_query(
        "SELECT DISTINCT date_week FROM questions ORDER BY date_week DESC", con
    )
    con.close()
    return df["date_week"].tolist()


def list_answer_dates():
    con = get_con()
    df = pd.read_sql_query(
        "SELECT DISTINCT date_week FROM answers ORDER BY date_week DESC", con
    )
    con.close()
    return df["date_week"].tolist()


def save_answers(student_id, date_week, qa_list, group_name=""):
    con = get_con()
    cur = con.cursor()
    cur.execute(
        "DELETE FROM answers WHERE student_id=? AND date_week=?",
        (student_id, date_week),
    )
    for qno, qtext, ans in qa_list:
        cur.execute(
            "INSERT INTO answers (student_id, date_week, question_no, question, answer, group_name, checked) VALUES (?,?,?,?,?,?,0)",
            (student_id, date_week, qno, qtext, ans, group_name.strip()),
        )
    con.commit()
    con.close()


def load_answers(date_week=None, student_search=""):
    con = get_con()
    where, params = [], []
    if date_week:
        where.append("date_week = ?")
        params.append(date_week)
    if student_search:
        where.append("student_id LIKE ?")
        params.append(f"%{student_search}%")
    wh = (" WHERE " + " AND ".join(where)) if where else ""
    df = pd.read_sql_query(
        f"SELECT id, student_id, date_week, question_no, question, answer, group_name, checked FROM answers{wh} ORDER BY student_id, question_no",
        con,
        params=params,
    )
    con.close()
    return df


def update_checked(ids, checked=True):
    if not ids:
        return
    con = get_con()
    cur = con.cursor()
    cur.execute(
        f"UPDATE answers SET checked = ? WHERE id IN ({','.join(['?'] * len(ids))})",
        [1 if checked else 0, *ids],
    )
    con.commit()
    con.close()


def log_student_login(student_id: str, date_week: str) -> None:
    """Record a student login for the activity scoring list."""
    if not student_id or not date_week:
        return
    con = get_con()
    cur = con.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO student_logins (student_id, date_week) VALUES (?, ?)",
        (student_id, date_week),
    )
    con.commit()
    con.close()


def list_logged_students(date_week: str | None = None) -> pd.DataFrame:
    """Return DataFrame of students who pressed Login."""
    con = get_con()
    if date_week:
        df = pd.read_sql_query(
            "SELECT student_id, date_week, logged_at FROM student_logins WHERE date_week=? ORDER BY logged_at",
            con,
            params=[date_week],
        )
    else:
        df = pd.read_sql_query(
            "SELECT student_id, date_week, logged_at FROM student_logins ORDER BY logged_at DESC",
            con,
        )
    con.close()
    return df


def load_class_scores(date_week: str | None) -> pd.DataFrame:
    con = get_con()
    if date_week:
        df = pd.read_sql_query(
            "SELECT student_id, date_week, score, note FROM class_scores WHERE date_week=?",
            con,
            params=[date_week],
        )
    else:
        df = pd.read_sql_query(
            "SELECT student_id, date_week, score, note FROM class_scores",
            con,
        )
    con.close()
    return df


def save_class_scores(date_week: str, score_rows) -> None:
    """
    score_rows: iterable of (student_id, score, note)
    """
    con = get_con()
    cur = con.cursor()
    for student_id, score, note in score_rows:
        cur.execute(
            "INSERT INTO class_scores (student_id, date_week, score, note) VALUES (?,?,?,?)",
            (student_id, date_week, score, note),
        )
    con.commit()
    con.close()


def load_participation_counts(date_week: str | None) -> dict[str, int]:
    """Return participation count per student for a given date."""
    if not date_week:
        return {}
    con = get_con()
    df = pd.read_sql_query(
        "SELECT student_id, participation FROM participation WHERE date_week=?",
        con,
        params=[date_week],
    )
    con.close()
    if df.empty:
        return {}
    return dict(zip(df["student_id"], df["participation"]))


def save_participation_counts(date_week: str, participation_rows) -> None:
    """
    participation_rows: iterable of (student_id, participation_count)
    """
    con = get_con()
    cur = con.cursor()
    for student_id, count in participation_rows:
        cur.execute(
            "INSERT INTO participation (student_id, date_week, participation) VALUES (?,?,?)",
            (student_id, date_week, int(count)),
        )
    con.commit()
    con.close()


def load_answer_counts(date_week: str | None) -> dict[str, int]:
    """Return number of answers submitted per student for given date."""
    if not date_week:
        return {}
    con = get_con()
    df = pd.read_sql_query(
        "SELECT student_id, COUNT(*) AS total FROM answers WHERE date_week=? GROUP BY student_id",
        con,
        params=[date_week],
    )
    con.close()
    if df.empty:
        return {}
    return dict(zip(df["student_id"], df["total"]))


def load_student_groups(date_week: str | None) -> dict[str, str]:
    """Return mapping of student_id -> group_name for a given date."""
    if not date_week:
        return {}
    con = get_con()
    df = pd.read_sql_query(
        """
        SELECT student_id, MAX(COALESCE(group_name, '')) AS group_name
        FROM answers
        WHERE date_week=?
        GROUP BY student_id
        """,
        con,
        params=[date_week],
    )
    con.close()
    if df.empty:
        return {}
    return dict(zip(df["student_id"], df["group_name"]))


def load_score_weights() -> tuple[float, float, float]:
    """
    (still exists in DB but NOT used in Score Overview now)
    """
    con = get_con()
    df = pd.read_sql_query(
        "SELECT w_answers, w_class, w_part FROM score_weights WHERE id = 1",
        con,
    )
    con.close()
    if df.empty:
        return 1.0, 1.0, 1.0
    row = df.iloc[0]
    w_answers = row["w_answers"] if row["w_answers"] is not None else 1.0
    w_class = row["w_class"] if row["w_class"] is not None else 1.0
    w_part = row["w_part"] if row["w_part"] is not None else 1.0
    return float(w_answers), float(w_class), float(w_part)


def save_score_weights(w_answers: float, w_class: float, w_part: float) -> None:
    con = get_con()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO score_weights (id, w_answers, w_class, w_part)
        VALUES (1, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            w_answers = excluded.w_answers,
            w_class = excluded.w_class,
            w_part = excluded.w_part
        """,
        (float(w_answers), float(w_class), float(w_part)),
    )
    con.commit()
    con.close()


# ---------- App ----------
init_db()
st.set_page_config(page_title="DADS9 - 5002 Score", page_icon="✅", layout="centered")

# session defaults
st.session_state.setdefault("started", False)
st.session_state.setdefault("q_index", 0)
st.session_state.setdefault("answers", DEFAULT_QUESTIONS.copy())
st.session_state.setdefault("show_preview", False)
st.session_state.setdefault("teacher_loaded", False)
st.session_state.setdefault("current_questions", DEFAULT_QUESTIONS.copy())
st.session_state.setdefault("allow_edit_question", True)
st.session_state.setdefault("group_name", "")
st.session_state.setdefault("answers_export_df", None)
st.session_state.setdefault("answers_export_label", "all")

st.title("📚 DADS9 - 5002 Score")

# 4 pages: Student, Teacher, Teacher (Participation), Teacher (Score Overview)
tab_student, tab_teacher, tab_teacher_part, tab_teacher_total = st.tabs(
    [
        "👩‍🎓 Student",
        "👨‍🏫 Teacher",
        "👨‍🏫 Teacher (Student Participation)",
        "👨‍🏫 Teacher (Score Overview)",
    ]
)


# ---------------- Student ----------------
with tab_student:
    st.subheader("Start")
    col1, col2 = st.columns(2)
    with col1:
        student_id = st.text_input("Student ID", placeholder="e.g., S001")
    with col2:
        date_week = st.text_input(
            "Date / Week",
            value=str(date.today()),
            help="Use same label as teacher's question set.",
        )

    start_col, login_col = st.columns([1, 1])
    with start_col:
        start = st.button("✅ START", use_container_width=True)
    with login_col:
        login_clicked = st.button("🔐 LOGIN", use_container_width=True)

    selected_date = date_week.strip() or str(date.today())

    if login_clicked:
        if not student_id.strip():
            st.warning("Please enter Student ID before logging in.")
        else:
            log_student_login(student_id.strip(), selected_date)
            st.success("Login sent to teacher for attendance/scoring.")

    if start:
        if not student_id.strip():
            st.warning("Please enter Student ID.")
        else:
            question_set = load_questions(selected_date)
            if not question_set:
                question_set = [""]
            st.session_state.current_questions = question_set
            st.session_state.answers = [""] * len(question_set)
            st.session_state.q_index = 0
            st.session_state.started = True
            st.session_state.show_preview = False
            st.session_state.group_name = ""
            st.session_state.pop("group_name_input", None)

    if st.session_state.started:
        st.divider()
        questions = st.session_state.get("current_questions", DEFAULT_QUESTIONS).copy()
        total = len(questions)

        if total <= 0:
            questions = [""]
            total = 1
            st.session_state.current_questions = questions
            st.session_state.answers = [""]

        q_idx = max(0, min(st.session_state.q_index, total - 1))
        st.session_state.q_index = q_idx
        progress_value = max(0.0, min((q_idx + 1) / total, 1.0))
        st.progress(progress_value, text=f"ข้อ {q_idx + 1}")

        key_q = f"q_{q_idx}"
        edited_q = st.text_input(
            "Question",
            value=questions[q_idx],
            key=key_q,
            placeholder="Type your question here",
        )
        questions[q_idx] = edited_q
        st.session_state.current_questions = questions

        if len(st.session_state.answers) != total:
            st.session_state.answers = (st.session_state.answers + [""] * total)[:total]
        key_a = f"a_{q_idx}"
        st.session_state.answers[q_idx] = st.text_area(
            "Your Answer", value=st.session_state.answers[q_idx], height=140, key=key_a
        )

        group_value = st.text_input(
            "Group Name (optional)",
            key="group_name_input",
            help="Leave blank if not applicable.",
        )
        st.session_state.group_name = group_value.strip()

        current_a_filled = st.session_state.answers[q_idx].strip() != ""
        allow_next = current_a_filled

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("⬅️ Back", use_container_width=True, disabled=(q_idx == 0)):
                st.session_state.q_index = max(0, q_idx - 1)
                st.session_state.show_preview = False
        with c2:
            if st.button(
                "➡️ Next",
                use_container_width=True,
                disabled=(q_idx >= total - 1) or (not allow_next),
                key=f"next_btn_{q_idx}",
            ):
                st.session_state.q_index = min(total - 1, q_idx + 1)
