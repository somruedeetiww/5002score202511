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
    Load global weighting scheme (w_answers, w_class, w_part).
    If none is saved yet, return (1.0, 1.0, 1.0).
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
    """
    Save global weighting scheme so it is reused in future sessions.
    """
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

# 4 pages: Student, Teacher, Teacher (Participation), Teacher (Total Score – All Time)
tab_student, tab_teacher, tab_teacher_part, tab_teacher_total = st.tabs(
    [
        "👩‍🎓 Student",
        "👨‍🏫 Teacher",
        "👨‍🏫 Teacher (Student Participation)",
        "👨‍🏫 Teacher (Total Score – All Time)",
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

        # Ensure at least 1
        if total <= 0:
            questions = [""]
            total = 1
            st.session_state.current_questions = questions
            st.session_state.answers = [""]

        q_idx = max(0, min(st.session_state.q_index, total - 1))
        st.session_state.q_index = q_idx
        progress_value = max(0.0, min((q_idx + 1) / total, 1.0))
        st.progress(progress_value, text=f"ข้อ {q_idx + 1}")

        # Editable question text (per submission)
        key_q = f"q_{q_idx}"
        edited_q = st.text_input(
            "Question",
            value=questions[q_idx],
            key=key_q,
            placeholder="Type your question here",
        )
        questions[q_idx] = edited_q
        st.session_state.current_questions = questions

        # Answer box
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

        # Validation for current step: ONLY require answer for Next
        current_a_filled = st.session_state.answers[q_idx].strip() != ""
        allow_next = current_a_filled

        # Controls row (Back / Next)
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
                # Move to next existing question; do NOT auto-add a new blank question
                st.session_state.q_index = min(total - 1, q_idx + 1)
                st.session_state.show_preview = False
                st.rerun()

        # Button to add a brand-new question at the end
        if st.button("➕ Add Question", use_container_width=True):
            st.session_state.current_questions.append("")
            st.session_state.answers.append("")
            st.session_state.q_index = len(st.session_state.current_questions) - 1
            st.session_state.show_preview = False
            st.rerun()

        # Check if all ANSWERS are filled (question text may be blank, that's ok)
        all_filled = all(
            a.strip() != ""
            for a in st.session_state.answers[: len(st.session_state.current_questions)]
        )

        # Preview & submit buttons
        if st.button("👁️ Preview", use_container_width=True, disabled=not all_filled):
            st.session_state.show_preview = True
        if not all_filled:
            st.info("กรุณากรอก 'คำตอบ' ให้ครบทุกข้อก่อนกด Preview/Submit")

        if st.session_state.get("show_preview"):
            st.subheader("Preview & Submit")
            questions = st.session_state.current_questions
            total = len(questions)
            df_prev = pd.DataFrame(
                {
                    "Question No.": list(range(1, total + 1)),
                    "Question": questions,
                    "Answer": st.session_state.answers[:total],
                    "Group": [st.session_state.get("group_name", "")] * total,
                }
            )
            st.dataframe(df_prev, use_container_width=True, hide_index=True)
            colp1, colp2 = st.columns([2, 1])
            with colp2:
                if st.button(
                    "🟦 SUBMIT", use_container_width=True, disabled=not all_filled
                ):
                    qa = [
                        (
                            i + 1,
                            (questions[i] or "").strip(),
                            st.session_state.answers[i].strip(),
                        )
                        for i in range(total)
                    ]
                    save_answers(
                        student_id.strip(),
                        date_week.strip(),
                        qa,
                        st.session_state.get("group_name", ""),
                    )
                    st.success("Your answers have been submitted successfully!")
                    # reset for new submission
                    st.session_state.started = False
                    st.session_state.q_index = 0
                    st.session_state.answers = [""] * len(DEFAULT_QUESTIONS)
                    st.session_state.show_preview = False
                    st.session_state.group_name = ""
                    st.session_state.pop("group_name_input", None)


# ---------------- Teacher (questions & checking) ----------------
with tab_teacher:
    st.subheader("Manage Questions & Check Answers")
    access_code = st.text_input(
        "Teacher Access Code", type="password", placeholder="Enter password"
    )

    if access_code.strip() != "1234":
        st.info("กรุณากรอกรหัสผ่าน เพื่อจัดการชุดคำถามและตรวจคำตอบ")
    else:
        m1, m2 = st.columns([1, 1])
        with m1:
            teacher_name = st.text_input("Teacher Name", placeholder="e.g., Ms. June")
        with m2:
            manage_date = st.text_input(
                "Date / Week (for Question Set)", value=str(date.today())
            )

        with st.expander("📝 Edit Question Set for this Date/Week", expanded=True):
            existing_dates = list_question_dates()
            if existing_dates:
                st.caption("Load from saved sets:")
                load_select = st.selectbox(
                    "Saved dates", options=["(select)"] + existing_dates, index=0
                )
                if load_select != "(select)":
                    manage_date = load_select
                    st.session_state["tmp_questions"] = load_questions(manage_date)

            if "tmp_questions" not in st.session_state:
                st.session_state["tmp_questions"] = load_questions(manage_date)

            num = st.number_input(
                "Number of questions",
                min_value=1,
                max_value=30,
                value=len(st.session_state["tmp_questions"]),
                step=1,
            )
            qlist = st.session_state["tmp_questions"]
            if len(qlist) < num:
                qlist = qlist + [""] * (num - len(qlist))
            elif len(qlist) > num:
                qlist = qlist[:num]

            new_questions = []
            for i in range(int(num)):
                new_questions.append(
                    st.text_input(
                        f"Q{i + 1}",
                        value=qlist[i],
                        placeholder=f"Enter question {i + 1}",
                    )
                )
            st.session_state["tmp_questions"] = new_questions

            cqs1, cqs2 = st.columns([1, 1])
            with cqs1:
                if st.button("💾 Save Question Set", use_container_width=True):
                    save_question_set(manage_date.strip(), new_questions)
                    st.success(
                        f"Saved {len(new_questions)} questions for {manage_date}."
                    )
            with cqs2:
                if st.button("🔄 Reset to Default", use_container_width=True):
                    st.session_state["tmp_questions"] = DEFAULT_QUESTIONS.copy()

        st.divider()

        c1, c2 = st.columns([2, 1])
        with c1:
            filter_date = st.text_input(
                "Filter Date / Week", value=manage_date, placeholder="YYYY-MM-DD"
            )
        with c2:
            start_check = st.button("✅ START (Load)", use_container_width=True)

        answer_dates = list_answer_dates()
        effective_filter = filter_date.strip()
        if answer_dates:
            history_options = ["ใช้วันที่กรอกด้านบน", "ดูทุกวัน"] + answer_dates
            selected_history = st.selectbox(
                "เลือกจากประวัติคำตอบ",
                history_options,
                index=0,
                key="answer_history_select",
            )
            if selected_history == "ดูทุกวัน":
                effective_filter = ""
            elif selected_history != "ใช้วันที่กรอกด้านบน":
                effective_filter = selected_history

        if start_check:
            st.session_state.teacher_loaded = True

        if st.session_state.get("teacher_loaded"):
            df = load_answers(effective_filter or None)
            if df.empty:
                st.info(
                    "No data found. Try adjusting filters or ask students to submit."
                )
                st.session_state["answers_export_df"] = None
                st.session_state["answers_export_label"] = effective_filter or "all"
            else:
                display_df = df.drop(columns=["checked"]) if "checked" in df else df
                counts_df = (
                    display_df.groupby(["student_id", "date_week"])
                    .size()
                    .reset_index(name="Answer Count")
                )
                display_df = display_df.merge(
                    counts_df, how="left", on=["student_id", "date_week"]
                )

                # Load activity scores (from class_scores) and merge
                class_scores_df = load_class_scores(None)
                if not class_scores_df.empty:
                    class_scores_df = class_scores_df.rename(
                        columns={"score": "Activity Score"}
                    )
                    display_df = display_df.merge(
                        class_scores_df[["student_id", "date_week", "Activity Score"]],
                        how="left",
                        on=["student_id", "date_week"],
                    )
                else:
                    display_df["Activity Score"] = 0.0

                display_df["Answer Count"] = (
                    display_df["Answer Count"].fillna(0).astype(int)
                )
                display_df["Activity Score"] = (
                    display_df["Activity Score"].fillna(0.0).round(2)
                )

                st.dataframe(display_df, hide_index=True, use_container_width=True)
                st.session_state["answers_export_df"] = display_df
                st.session_state["answers_export_label"] = effective_filter or "all"

        # Activity Score input (float) section
        with st.expander("📝 Activity Score (per date)", expanded=False):
            score_date = manage_date.strip()

            # Gather students who have answers, logins, or existing scores on this date
            answers_df_date = load_answers(score_date)
            ans_ids = (
                set(answers_df_date["student_id"].tolist())
                if not answers_df_date.empty
                else set()
            )

            logged_students = list_logged_students(score_date)
            login_ids = (
                set(logged_students["student_id"].tolist())
                if not logged_students.empty
                else set()
            )

            scores_df = load_class_scores(score_date)
            score_ids = (
                set(scores_df["student_id"].tolist()) if not scores_df.empty else set()
            )

            all_ids = sorted(ans_ids | login_ids | score_ids)

            if not all_ids:
                st.info("ยังไม่มีนักเรียนที่มีคำตอบ / Login / คะแนนกิจกรรม สำหรับวันที่นี้")
            else:
                existing_scores = (
                    {row["student_id"]: row["score"] for _, row in scores_df.iterrows()}
                    if not scores_df.empty
                    else {}
                )

                st.markdown("**กำหนด Activity Score (สามารถใส่ทศนิยมได้ เช่น 0.50, 1.25)**")
                score_rows_input = []

                for sid in all_ids:
                    cols = st.columns([3, 2])
                    cols[0].write(sid)
                    val = cols[1].number_input(
                        "Score",
                        key=f"activity_score_{score_date}_{sid}",
                        value=float(existing_scores.get(sid, 0.0)),
                        step=0.01,
                        format="%.2f",
                    )
                    score_rows_input.append((sid, val))

                if st.button("💾 Save Activity Scores", use_container_width=True):
                    rows_to_save = [
                        (sid, float(val), "") for sid, val in score_rows_input
                    ]
                    save_class_scores(score_date, rows_to_save)
                    st.success("บันทึก Activity Score สำหรับวันที่นี้เรียบร้อยแล้ว ✅")

        st.caption(
            "Tip: Students can append extra questions before submitting. Default question set is provided by the teacher per Date/Week."
        )


# ---------------- Teacher (Student Participation page) ----------------
with tab_teacher_part:
    st.subheader("Student Participation (per date)")
    access_code_part = st.text_input(
        "Teacher Access Code",
        type="password",
        placeholder="Enter password",
        key="access_code_participation",
    )

    if access_code_part.strip() != "1234":
        st.info("กรุณากรอกรหัสผ่าน เพื่อดูและบันทึกการมีส่วนร่วมของนักเรียน")
    else:
        participation_date = st.text_input(
            "Date / Week (for Participation)",
            value=str(date.today()),
            key="participation_date_input",
            help="Use the same label that students selected when they pressed LOGIN.",
        )

        participation_date = participation_date.strip()
        if not participation_date:
            st.info("กรุณากรอกวันที่ / สัปดาห์ ก่อน")
        else:
            logged_students = list_logged_students(participation_date)
            existing_part = load_participation_counts(participation_date)

            ids_from_login = (
                logged_students["student_id"].tolist()
                if not logged_students.empty
                else []
            )
            all_ids = sorted(set(ids_from_login) | set(existing_part.keys()))

            if not all_ids:
                st.info("ยังไม่มีนักเรียนกด LOGIN สำหรับวันที่นี้")
            else:
                state_key = f"participation_values_{participation_date}"
                if (state_key not in st.session_state) or (
                    st.session_state.get("participation_date") != participation_date
                ):
                    st.session_state["participation_date"] = participation_date
                    st.session_state[state_key] = {
                        sid: existing_part.get(sid, 0) for sid in all_ids
                    }
                else:
                    for sid in all_ids:
                        st.session_state[state_key].setdefault(
                            sid, existing_part.get(sid, 0)
                        )

                part_map = st.session_state[state_key]

                st.markdown("**รายการนักเรียนที่กด LOGIN และจำนวนครั้งที่มีส่วนร่วมในคาบ**")

                hcols = st.columns([3, 1, 1, 1])
                hcols[0].markdown("**Student ID**")
                hcols[1].markdown("**−**")
                hcols[2].markdown("**Participation**")
                hcols[3].markdown("**+**")

                for sid in all_ids:
                    cols = st.columns([3, 1, 1, 1])
                    cols[0].write(sid)

                    if cols[1].button(
                        "➖",
                        key=f"part_minus_{participation_date}_{sid}",
                    ):
                        part_map[sid] = max(0, part_map.get(sid, 0) - 1)
                        st.session_state[state_key] = part_map
                        st.rerun()

                    cols[2].markdown(
                        f"<div style='text-align:center;font-weight:bold;'>{part_map.get(sid, 0)}</div>",
                        unsafe_allow_html=True,
                    )

                    if cols[3].button(
                        "➕",
                        key=f"part_plus_{participation_date}_{sid}",
                    ):
                        part_map[sid] = part_map.get(sid, 0) + 1
                        st.session_state[state_key] = part_map
                        st.rerun()

                summary_rows_part = [
                    {"Student ID": sid, "Participation": part_map.get(sid, 0)}
                    for sid in all_ids
                ]
                summary_df_part = pd.DataFrame(summary_rows_part)
                st.markdown("**สรุปจำนวนครั้งที่มีส่วนร่วมตามนักเรียน**")
                st.dataframe(
                    summary_df_part,
                    hide_index=True,
                    use_container_width=True,
                )

                if st.button(
                    "💾 Save Participation",
                    use_container_width=True,
                    key="save_participation_btn",
                ):
                    rows = [(sid, part_map.get(sid, 0)) for sid in all_ids]
                    save_participation_counts(participation_date, rows)
                    st.success("บันทึกจำนวนครั้งที่มีส่วนร่วมของนักเรียนเรียบร้อยแล้ว")


# ---------------- Teacher (Total Score – All Time) ----------------
with tab_teacher_total:
    st.subheader("Total Score – All Time (Answers + Activity Score + Participation)")
    access_code_total = st.text_input(
        "Teacher Access Code",
        type="password",
        placeholder="Enter password",
        key="access_code_total",
    )

    if access_code_total.strip() != "1234":
        st.info("กรุณากรอกรหัสผ่าน เพื่อดูคะแนนรวมของนักเรียน")
    else:
        st.caption(
            "คะแนนรวมสะสมจากทุกวันที่มีข้อมูล: "
            "จำนวนคำตอบ (Answers) + Activity Score + การมีส่วนร่วม (Participation)."
        )

        con = get_con()

        df_ans = pd.read_sql_query(
            "SELECT student_id, COUNT(*) AS Answers FROM answers GROUP BY student_id",
            con,
        )

        df_cls = pd.read_sql_query(
            "SELECT student_id, SUM(score) AS ActivityScore FROM class_scores GROUP BY student_id",
            con,
        )

        df_part = pd.read_sql_query(
            "SELECT student_id, SUM(participation) AS Participation "
            "FROM participation GROUP BY student_id",
            con,
        )

        df_group = pd.read_sql_query(
            """
            SELECT student_id, MAX(COALESCE(group_name, '')) AS group_name
            FROM answers
            GROUP BY student_id
            """,
            con,
        )

        con.close()

        answer_counts_all = (
            dict(zip(df_ans["student_id"], df_ans["Answers"]))
            if not df_ans.empty
            else {}
        )
        activity_scores_all = (
            dict(zip(df_cls["student_id"], df_cls["ActivityScore"]))
            if not df_cls.empty
            else {}
        )
        participation_all = (
            dict(zip(df_part["student_id"], df_part["Participation"]))
            if not df_part.empty
            else {}
        )
        group_map_all = (
            dict(zip(df_group["student_id"], df_group["group_name"]))
            if not df_group.empty
            else {}
        )

        all_ids = sorted(
            set(answer_counts_all.keys())
            | set(activity_scores_all.keys())
            | set(participation_all.keys())
            | set(group_map_all.keys())
        )

        if not all_ids:
            st.info("ยังไม่มีข้อมูลคะแนนรวม (ยังไม่มีคำตอบ Activity Score หรือการมีส่วนร่วมในระบบ)")
        else:
            db_w_answers, db_w_class, db_w_part = load_score_weights()

            if "w_answers_all" not in st.session_state:
                st.session_state["w_answers_all"] = db_w_answers
            if "w_class_all" not in st.session_state:
                st.session_state["w_class_all"] = db_w_class
            if "w_part_all" not in st.session_state:
                st.session_state["w_part_all"] = db_w_part

            st.markdown("### 🎚 Weighting Scheme")
            c_w1, c_w2, c_w3 = st.columns(3)
            with c_w1:
                w_answers = st.number_input(
                    "Weight: Answers",
                    value=float(st.session_state["w_answers_all"]),
                    step=0.1,
                    key="w_answers_all",
                )
            with c_w2:
                w_class = st.number_input(
                    "Weight: Activity Score",
                    value=float(st.session_state["w_class_all"]),
                    step=0.1,
                    key="w_class_all",
                )
            with c_w3:
                w_part = st.number_input(
                    "Weight: Participation",
                    value=float(st.session_state["w_part_all"]),
                    step=0.1,
                    key="w_part_all",
                )

            st.caption(
                f"สูตร: Final Score = Answers × {w_answers} + Activity Score × {w_class} + Participation × {w_part}"
            )

            if st.button("💾 Save weights as default", use_container_width=True):
                save_score_weights(w_answers, w_class, w_part)
                st.success("บันทึกค่าน้ำหนักเป็นค่าเริ่มต้นสำหรับครั้งถัดไปเรียบร้อยแล้ว ✅")

            rows = []
            for sid in all_ids:
                ans = answer_counts_all.get(sid, 0)
                act = activity_scores_all.get(sid, 0.0) or 0.0
                part = participation_all.get(sid, 0) or 0
                group_label = (group_map_all.get(sid, "") or "").strip()

                total_raw = ans + act + part
                final_score = ans * w_answers + act * w_class + part * w_part

                rows.append(
                    {
                        "Student ID": sid,
                        "Group": group_label,
                        "Answers": ans,
                        "Activity Score": round(act, 2),
                        "Participation": part,
                        "Total (raw)": total_raw,
                        "Final Score": round(final_score, 2),
                    }
                )

            total_df = pd.DataFrame(rows)

            st.markdown("### 📊 คะแนนรวมสะสมตามนักเรียน (ทุกครั้งที่ให้คะแนน)")
            st.dataframe(
                total_df,
                hide_index=True,
                use_container_width=True,
            )

            if not total_df.empty:
                group_df = (
                    total_df.assign(
                        Group=total_df["Group"].apply(
                            lambda g: g if g else "ไม่ระบุกลุ่ม"
                        )
                    )
                    .groupby("Group", as_index=False)
                    .agg(
                        Members=("Student ID", "count"),
                        Answers=("Answers", "sum"),
                        ActivityScore=("Activity Score", "sum"),
                        Participation=("Participation", "sum"),
                        TotalRaw=("Total (raw)", "sum"),
                        FinalScore=("Final Score", "sum"),
                    )
                )
                group_df.rename(
                    columns={
                        "ActivityScore": "Activity Score",
                        "TotalRaw": "Total (raw)",
                        "FinalScore": "Final Score",
                    },
                    inplace=True,
                )

                st.markdown("### 👥 สรุปคะแนนรวมสะสมตามกลุ่ม")
                st.dataframe(
                    group_df,
                    hide_index=True,
                    use_container_width=True,
                )

            csv_total = total_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Export Total Score CSV (All Dates, with Final Score)",
                csv_total,
                file_name="total_scores_all_dates_with_final_score.csv",
                mime="text/csv",
                use_container_width=True,
                key="export_total_scores_csv",
            )
