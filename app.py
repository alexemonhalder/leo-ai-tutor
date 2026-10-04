import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from crew.tutor_crew import MAX_ROUNDS, TutorCrew, TutorError  # noqa: E402
from memory.student_memory import StudentMemory  # noqa: E402

st.set_page_config(page_title="Leo - Multi-Agent AI Tutor", page_icon="🦁", layout="wide")

LETTERS = "ABCD"
ICONS = {
    "Coordinator": "🧭",
    "Explainer": "📘",
    "Quiz Master": "📝",
    "Evaluator": "✅",
}
memory = StudentMemory()

DEFAULTS = {
    "stage": "start",      # start | clarify | learn | feedback
    "name": "",
    "request": "",
    "level": "beginner",
    "topic": "",
    "plan": None,
    "explanation": None,
    "quiz": None,
    "result": None,
    "round": 1,
    "trace": [],
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


def reset_session():
    keep = st.session_state.trace
    for key, value in DEFAULTS.items():
        st.session_state[key] = value
    st.session_state.trace = keep


def make_tutor(status=None) -> TutorCrew:
    def on_event(agent: str, message: str):
        st.session_state.trace.append((agent, message))
        if status is not None:
            status.write(f"{ICONS.get(agent, '🤖')} **{agent}**: {message}")
    return TutorCrew(on_event=on_event)


def run_plan(request: str):
    name = st.session_state.name
    with st.status("Leo's team is working...", expanded=True) as status:
        tutor = make_tutor(status)
        try:
            plan = tutor.plan(name, request, memory.summary(name))
            st.session_state.plan = plan
            st.session_state.request = request
            if not plan.is_clear:
                st.session_state.stage = "clarify"
                status.update(label="Coordinator needs more info", state="complete")
                return
            st.session_state.topic = plan.topic
            status.update(label="Plan ready", state="complete")
        except TutorError as err:
            status.update(label="Something went wrong", state="error")
            st.error(f"🧭 Coordinator: {err}")
            return
    run_lesson(focus=None, note="")


def run_lesson(focus, note):
    name = st.session_state.name
    with st.status("Explainer and Quiz Master are preparing your lesson...", expanded=True) as status:
        tutor = make_tutor(status)
        try:
            explanation, quiz = tutor.teach_and_quiz(
                name, st.session_state.topic, st.session_state.level,
                memory.summary(name), focus_concepts=focus, student_note=note,
                round_number=st.session_state.round,
            )
        except TutorError as err:
            status.update(label="Something went wrong", state="error")
            st.error(f"🧭 Coordinator: {err}")
            return
        st.session_state.explanation = explanation
        st.session_state.quiz = quiz
        st.session_state.result = None
        st.session_state.stage = "learn"
        status.update(label="Lesson and quiz ready", state="complete")
    st.rerun()


def run_evaluation(answers):
    name = st.session_state.name
    with st.status("Evaluator is checking your answers...", expanded=True) as status:
        tutor = make_tutor(status)
        result = tutor.evaluate(name, st.session_state.quiz, answers)
        memory.record_result(
            name, st.session_state.topic, st.session_state.level,
            result.score, result.total, result.weak_concepts,
        )
        if not result.weak_concepts:
            memory.clear_weak(name, [q.concept for q in st.session_state.quiz.questions])
        st.session_state.result = result
        st.session_state.stage = "feedback"
        status.update(label="Feedback ready", state="complete")
    st.rerun()


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.title("🦁 Leo")
    st.caption("Multi-agent AI tutor (CrewAI)")
    st.subheader("Agent activity")
    if not st.session_state.trace:
        st.write("No activity yet.")
    for agent, message in st.session_state.trace[-14:]:
        st.write(f"{ICONS.get(agent, '🤖')} **{agent}**: {message}")
    if st.session_state.name:
        st.subheader("Student memory")
        st.write(memory.summary(st.session_state.name))
    if st.button("Start over"):
        reset_session()
        st.rerun()

st.header("Leo - your study team")

# ------------------------------------------------------------------ start
if st.session_state.stage == "start":
    st.write("Tell Leo what you want to learn. The Coordinator will plan, "
             "the Explainer will teach, the Quiz Master will test you, and the "
             "Evaluator will give feedback.")
    with st.form("start_form"):
        name = st.text_input("Your name", value=st.session_state.name)
        level = st.selectbox("Your level", ["beginner", "intermediate", "advanced"])
        request = st.text_area("What do you want to learn?", placeholder="e.g. Explain photosynthesis")
        go = st.form_submit_button("Start learning")
    if go:
        if not name.strip():
            st.warning("Please enter your name.")
        else:
            st.session_state.name = name.strip()
            st.session_state.level = level
            run_plan(request)
            if st.session_state.stage == "clarify":
                st.rerun()

# ------------------------------------------------------------------ clarify
elif st.session_state.stage == "clarify":
    plan = st.session_state.plan
    st.info(f"🧭 Coordinator: {plan.clarification_question or 'Which topic should we start with?'}")
    with st.form("clarify_form"):
        extra = st.text_input("Your answer")
        go = st.form_submit_button("Send")
    if go and extra.strip():
        run_plan(f"{st.session_state.request}. {extra}")
        if st.session_state.stage == "clarify":
            st.rerun()

# ------------------------------------------------------------------ learn
elif st.session_state.stage == "learn":
    exp = st.session_state.explanation
    quiz = st.session_state.quiz
    st.caption(f"Topic: {st.session_state.topic} | Round {st.session_state.round}")

    st.subheader(f"📘 Explainer: {exp.title}")
    st.write(exp.explanation)
    for point in exp.key_points:
        st.markdown(f"- {point}")
    st.markdown(f"**Example:** {exp.example}")

    with st.expander("✋ Step in: ask Leo to explain differently (human-in-the-loop)"):
        note = st.text_input("What should Leo change or focus on?",
                             placeholder="e.g. use a simpler analogy")
        if st.button("Re-explain with my note") and note.strip():
            run_lesson(focus=None, note=note)

    st.subheader("📝 Quiz Master: practice questions")
    with st.form("quiz_form"):
        picks = {}
        for q in quiz.questions:
            picks[q.id] = st.radio(f"{q.id}. {q.question}", q.options, index=None, key=f"q{q.id}")
        submit = st.form_submit_button("Submit answers")
    if submit:
        if any(v is None for v in picks.values()):
            st.warning("Please answer every question.")
        else:
            q_by_id = {q.id: q for q in quiz.questions}
            answers = {qid: LETTERS[q_by_id[qid].options.index(choice)]
                       for qid, choice in picks.items()}
            run_evaluation(answers)

# ------------------------------------------------------------------ feedback
elif st.session_state.stage == "feedback":
    result = st.session_state.result
    quiz = st.session_state.quiz
    st.subheader("✅ Evaluator: your feedback")
    st.metric("Score", f"{result.score} / {result.total}")
    st.write(result.overall_feedback)

    q_by_id = {q.id: q for q in quiz.questions}
    for fb in result.per_question:
        q = q_by_id.get(fb.question_id)
        icon = "✅" if fb.is_correct else "❌"
        st.markdown(f"{icon} **Q{fb.question_id}** ({fb.concept}): {q.question if q else ''}")
        st.write(fb.feedback)

    col1, col2 = st.columns(2)
    if result.needs_reteach and st.session_state.round < MAX_ROUNDS:
        st.warning("Some concepts need another pass: " + ", ".join(result.weak_concepts))
        if col1.button("🔁 Re-teach my weak areas"):
            st.session_state.round += 1
            run_lesson(focus=result.weak_concepts, note="")
    elif not result.needs_reteach:
        st.success("Great work! You passed this topic.")
    if col2.button("Learn something new"):
        reset_session()
        st.rerun()