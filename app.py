import base64
import asyncio
from pathlib import Path

import streamlit as st
from autogen_core import CancellationToken

from interviewer import create_interviewer


INTERVIEW_QUESTION_COUNT = 2


# =========================================================
# PAGE CONFIGURATION
# =========================================================

st.set_page_config(
    page_title="AI Interviewer",
    page_icon="🎯",
    layout="wide",
)

background_image = base64.b64encode(
    (Path(__file__).parent / "assets" / "interview-background.svg").read_bytes()
).decode("ascii")

st.markdown(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
        max-width: 1160px;
        margin-left: clamp(1rem, 4vw, 4rem);
        margin-right: auto;
        padding-top: 1.25rem;
    }

    [data-testid="stMainBlockContainer"] > div {
        gap: 0.4rem;
    }

    .app-heading {
        margin: 0 0 0.75rem;
    }

    .app-heading h1 {
        margin: 0;
        padding: 0;
        line-height: 1.15;
    }

    .app-heading p {
        margin: 0.25rem 0 0;
        opacity: 0.72;
        font-size: 0.9rem;
    }

    [data-testid="stAppViewContainer"] {
        background-color: var(--background-color);
        background-image:
            url("data:image/svg+xml;base64,__BACKGROUND_IMAGE__"),
            radial-gradient(
                ellipse at 10% 12%,
                rgba(129, 140, 248, 0.14),
                transparent 38rem
            ),
            radial-gradient(
                ellipse at 88% 82%,
                rgba(56, 189, 248, 0.12),
                transparent 36rem
            );
        background-position: center center, left top, right bottom;
        background-size: cover, auto, auto;
        background-repeat: no-repeat;
    }

    [data-testid="stHeader"] {
        background: transparent;
    }

    [data-testid="stChatMessage"] {
        border: 1px solid rgba(129, 140, 248, 0.32);
        border-radius: 1rem;
        padding: 0.85rem 1.1rem;
        margin-bottom: 0.45rem;
        background: rgba(238, 242, 255, 0.94);
        box-shadow: 0 8px 24px rgba(79, 70, 229, 0.08);
    }

    [data-testid="stVerticalBlockBorderWrapper"] {
        border-color: rgba(129, 140, 248, 0.24);
        border-radius: 1rem;
        background: rgba(255, 255, 255, 0.78);
        box-shadow: 0 18px 48px rgba(49, 46, 129, 0.075);
        backdrop-filter: blur(12px);
    }

    [data-testid="stTextInput"] input {
        border-radius: 0.75rem;
    }

    [data-testid="stButton"] button {
        border-radius: 0.75rem;
        font-weight: 600;
        padding: 0.55rem 1rem;
        transition: transform 120ms ease, box-shadow 120ms ease;
    }

    [data-testid="stButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 20px rgba(79, 70, 229, 0.18);
    }

    [data-testid="stProgress"] {
        margin: 0.75rem 0 1.5rem;
    }

    [data-testid="stChatInput"] {
        padding-top: 0.75rem;
    }

    @media (max-width: 768px) {
        [data-testid="stMainBlockContainer"] {
            margin-left: auto;
            margin-right: auto;
            padding-top: 1rem;
        }

        [data-testid="stAppViewContainer"] {
            background-size: auto 52%, auto, auto;
            background-position: right bottom, left top, right bottom;
        }
    }
    </style>
    """.replace("__BACKGROUND_IMAGE__", background_image),
    unsafe_allow_html=True,
)


# =========================================================
# SESSION STATE
# =========================================================

if "interview_started" not in st.session_state:
    st.session_state.interview_started = False

if "interview_ended" not in st.session_state:
    st.session_state.interview_ended = False

if "job_role" not in st.session_state:
    st.session_state.job_role = ""

if "question_number" not in st.session_state:
    st.session_state.question_number = 0

if "conversation" not in st.session_state:
    st.session_state.conversation = []

if "current_question" not in st.session_state:
    st.session_state.current_question = ""

if "feedback" not in st.session_state:
    st.session_state.feedback = ""

if "interviewer" not in st.session_state:
    st.session_state.interviewer = None

if "model_client" not in st.session_state:
    st.session_state.model_client = None


async def get_candidate_answer(
    prompt: str,
    cancellation_token: CancellationToken | None,
) -> str:
    answer = st.session_state.get("pending_answer")

    if answer is None:
        raise RuntimeError(
            "The candidate agent was called without a submitted answer."
        )

    del st.session_state["pending_answer"]
    return answer


def reset_interview():
    model_client = st.session_state.model_client
    loop = st.session_state.get("async_loop")

    if model_client is not None and loop is not None and not loop.is_closed():
        loop.run_until_complete(model_client.close())

    st.session_state.interview_started = False
    st.session_state.interview_ended = False
    st.session_state.job_role = ""
    st.session_state.question_number = 0
    st.session_state.conversation = []
    st.session_state.current_question = ""
    st.session_state.feedback = ""
    st.session_state.interviewer = None
    st.session_state.model_client = None

    for key in ("pending_answer", "job_role_input", "answer_1", "answer_2"):
        st.session_state.pop(key, None)


# =========================================================
# AUTO-GEN AI FUNCTION
# =========================================================

async def run_interview_turn(message=None):
    """
    Run the next agent in the interview team and extract its text response.
    """

    response = await st.session_state.interviewer.run(
        task=message
    )

    # Look backwards through the messages and find
    # the latest message containing actual text.
    for msg in reversed(response.messages):

        content = getattr(msg, "content", None)

        if isinstance(content, str) and content.strip():
            return content.strip()

    return (
        "Sorry, I could not generate a question. "
        "Please try again."
    )


def ask_ai(message):
    """
    Synchronous wrapper around one asynchronous team turn.
    """

    loop = st.session_state.get("async_loop")

    if loop is None or loop.is_closed():
        loop = asyncio.new_event_loop()
        st.session_state.async_loop = loop

    return loop.run_until_complete(
        run_interview_turn(message)
    )


def render_conversation():
    for item in st.session_state.conversation:
        with st.chat_message("assistant", avatar="🎯"):
            st.markdown(
                f"**Interviewer · Question "
                f"{item['question_number']}**"
            )
            st.write(item["question"])

        if item["answer"] is not None:
            with st.chat_message("user", avatar="👤"):
                st.markdown("**You**")
                st.write(item["answer"])


# =========================================================
# HEADER
# =========================================================

st.markdown(
    """
    <div class="app-heading">
        <h1>🎯 AI Interviewer</h1>
        <p>A focused practice space for your next interview.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# START INTERVIEW
# =========================================================

if not st.session_state.interview_started:

    with st.chat_message("assistant", avatar="🎯"):
        st.markdown("**AI Interviewer**")
        st.write(
            "Hi! I’ll ask two questions tailored to your role, "
            "then share friendly, practical feedback."
        )

    with st.container(border=True):
        st.subheader("Start your interview")

        job_role = st.text_input(
            "What role are you preparing for?",
            placeholder="e.g. Java Developer",
            key="job_role_input",
        )

        if st.button(
            "Start interview  →",
            type="primary",
        ):

            if not job_role.strip():

                st.warning(
                    "Please enter a job role first."
                )

            else:

                # Save job role
                st.session_state.job_role = (
                    job_role.strip()
                )

                # Create AutoGen interviewer
                (
                    st.session_state.interviewer,
                    st.session_state.model_client,
                ) = create_interviewer(get_candidate_answer)

                # Start interview
                st.session_state.interview_started = True

                # First question
                st.session_state.question_number = 1

                # Ask AI for first question
                first_question = ask_ai(
                    f"""
Start a technical/job interview.

Job Role:
{st.session_state.job_role}

This is Question 1 of {INTERVIEW_QUESTION_COUNT}.

Ask the candidate exactly ONE interview question.

Requirements:
- The question must be relevant to the job role.
- Do not provide the answer.
- Keep the question clear and conversational.
- Do not ask multiple questions.
"""
                )

                # Save question
                st.session_state.current_question = (
                    first_question
                )

                # Save conversation
                st.session_state.conversation.append(
                    {
                        "question_number": 1,
                        "question": first_question,
                        "answer": None,
                    }
                )

                st.rerun()


# =========================================================
# INTERVIEW SCREEN
# =========================================================

elif (
    st.session_state.interview_started
    and not st.session_state.interview_ended
):

    st.subheader(st.session_state.job_role)
    st.progress(
        st.session_state.question_number / INTERVIEW_QUESTION_COUNT,
        text=(
            f"Question {st.session_state.question_number} "
            f"of {INTERVIEW_QUESTION_COUNT}"
        ),
    )

    render_conversation()

    answer = st.chat_input(
        "Type your answer and press Enter...",
        key=f"answer_{st.session_state.question_number}",
    )

    if answer:

        if not answer.strip():

            st.warning(
                "Please enter your answer."
            )

        else:

            # Current question number
            current_question_number = (
                st.session_state.question_number
            )

            # Save candidate answer
            st.session_state.conversation[
                current_question_number - 1
            ]["answer"] = answer.strip()

            # Let the candidate proxy publish the submitted response.
            st.session_state.pending_answer = answer.strip()
            ask_ai(None)

            # =================================================
            # Final question → generate feedback
            # =================================================

            if current_question_number == INTERVIEW_QUESTION_COUNT:

                # Build complete interview history
                conversation_text = "\n\n".join(
                    [
                        (
                            f"Question "
                            f"{item['question_number']}: "
                            f"{item['question']}\n"
                            f"Candidate Answer: "
                            f"{item['answer']}"
                        )
                        for item
                        in st.session_state.conversation
                    ]
                )

                feedback_prompt = f"""
The candidate has completed all {INTERVIEW_QUESTION_COUNT} interview questions.

Job Role:
{st.session_state.job_role}

Complete Interview:

{conversation_text}

Now provide friendly and constructive feedback.

Your feedback should include:

1. Overall impression
2. Strengths
3. Areas for improvement
4. Encouraging final advice

Be supportive and professional.

Do not be overly harsh.

After the feedback, finish with exactly:

END OF INTERVIEW
"""

                # Ask AI for feedback
                feedback = ask_ai(
                    feedback_prompt
                )

                # Save feedback
                st.session_state.feedback = feedback

                # End interview
                st.session_state.interview_ended = True

                st.rerun()

            # =================================================
            # Generate the next question
            # =================================================

            else:

                next_question_number = (
                    current_question_number + 1
                )

                # Build previous conversation
                conversation_text = "\n\n".join(
                    [
                        (
                            f"Question "
                            f"{item['question_number']}: "
                            f"{item['question']}\n"
                            f"Candidate Answer: "
                            f"{item['answer']}"
                        )
                        for item
                        in st.session_state.conversation
                        if item["answer"] is not None
                    ]
                )

                next_question_prompt = f"""
Continue the interview.

Job Role:
{st.session_state.job_role}

You are now asking Question
{next_question_number} of {INTERVIEW_QUESTION_COUNT}.

Previous interview conversation:

{conversation_text}

Based on the candidate's previous answers,
ask the next relevant interview question.

Rules:

- Ask exactly ONE question.
- Do not provide the answer.
- Do not ask multiple questions.
- Keep the question relevant to the job role.
- Gradually increase the difficulty.
- Consider the candidate's previous answers.
- Do not repeat previous questions.
"""

                # Ask AI for next question
                next_question = ask_ai(
                    next_question_prompt
                )

                # Update question number
                st.session_state.question_number = (
                    next_question_number
                )

                # Update current question
                st.session_state.current_question = (
                    next_question
                )

                # Save next question
                st.session_state.conversation.append(
                    {
                        "question_number": (
                            next_question_number
                        ),
                        "question": next_question,
                        "answer": None,
                    }
                )

                st.rerun()


# =========================================================
# INTERVIEW COMPLETED
# =========================================================

elif st.session_state.interview_ended:

    st.subheader("🎉 Interview complete")

    with st.container(border=True):
        st.markdown("### Your interview feedback")
        st.markdown(st.session_state.feedback)

        if st.button(
            "↻  Start a new interview",
            type="primary",
            key="restart_interview",
        ):
            reset_interview()
            st.rerun()

    st.subheader("Your conversation")
    render_conversation()
