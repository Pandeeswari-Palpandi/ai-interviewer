import os
from collections.abc import Awaitable, Callable

from dotenv import load_dotenv
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_core import CancellationToken
from autogen_ext.models.openai import OpenAIChatCompletionClient


load_dotenv()


def create_interviewer(
    input_func: Callable[
        [str, CancellationToken | None], Awaitable[str]
    ],
):
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    interviewer = AssistantAgent(
        name="ai_interviewer",
        model_client=model_client,
        max_tool_iterations=5,
        system_message="""
                You are a friendly and professional AI interviewer.

                Your job is to conduct a technical/job interview based on the
                candidate's selected job role.

                Interview rules:

                1. Ask exactly ONE question at a time.
                2. The questions must be relevant to the candidate's job role.
                3. Start with a reasonably simple question and gradually increase
                the difficulty.
                4. Consider the candidate's previous answers when creating the
                next question.
                5. Do not ask multiple questions in one response.
                6. Keep questions clear and conversational.
                7. Do not provide the answer to the question.
                8. Do not end the interview yourself. The application controls
                when the interview ends.
                9. After receiving the candidate's second answer, provide friendly
                feedback about their overall performance.
                10. The feedback should mention:
                    - strengths
                    - areas for improvement
                    - overall impression
                    - an encouraging closing message

                Be friendly, supportive, and professional.

                IMPORTANT:
                The application will tell you when the candidate has completed
                the second question. When that happens, provide the feedback and
                finish your response with exactly:

                END OF INTERVIEW
                """,
    )

    candidate = UserProxyAgent(
        name="candidate",
        description="The human candidate answering interview questions.",
        input_func=input_func,
    )

    interview_team = RoundRobinGroupChat(
        participants=[interviewer, candidate],
        termination_condition=TextMentionTermination(
            "END OF INTERVIEW",
            sources=["ai_interviewer"],
        ),
        # Return control to Streamlit after each agent turn.
        max_turns=1,
    )

    return interview_team, model_client
