from langchain_core.messages import AIMessage, HumanMessage

from app.agent.state import AgentState
from app.services.llm import get_llm

_CLASSIFY_PROMPT = (
    "You are routing a Bible study chat message to the correct assistant mode.\n\n"
    "Modes:\n"
    "- bible_search: the user wants to look up a verse, find a passage, ask about a "
    "biblical character, event, or fact, or retrieve Scripture text.\n"
    "- study_coach: the user wants help memorizing Scripture, practising recitation, "
    "learning a memory technique, or being coached through remembering a verse.\n\n"
    "IMPORTANT CONTEXT RULE: If the previous assistant message was from the study coach "
    "(e.g. it asked the user to try reciting a verse, gave chunking/technique instructions, "
    "or asked 'say it back to me'), then the user's reply is almost certainly part of that "
    "coaching session — even if they are quoting Scripture text. Route it to study_coach.\n\n"
    "Only switch to bible_search if the user clearly changes topic "
    "(e.g. 'what does John 3:16 say?' or 'who was Moses?').\n\n"
    "Reply with ONLY the mode name: bible_search or study_coach. Nothing else."
)


def router_node(state: AgentState) -> dict:
    """
    Classifies the latest user message intent using conversation context
    so quoting a verse during a coaching session stays in study_coach.
    """
    messages = state["messages"]
    human_messages = [m for m in messages if isinstance(m, HumanMessage)]
    if not human_messages:
        return {"route": "bible_search"}

    user_text = human_messages[-1].content

    # Include the last AI message as context so the router knows if a coaching
    # session is already in progress
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    last_ai = ai_messages[-1].content if ai_messages else ""

    context_block = ""
    if last_ai:
        context_block = f"Previous assistant message:\n{last_ai[:400]}\n\n"

    llm = get_llm(temperature=0)
    result = llm.invoke(
        [
            HumanMessage(
                content=f"{_CLASSIFY_PROMPT}\n\n{context_block}User message: {user_text}"
            )
        ]
    )

    raw = result.content.strip().lower()
    route = "study_coach" if "study_coach" in raw else "bible_search"
    return {"route": route}
