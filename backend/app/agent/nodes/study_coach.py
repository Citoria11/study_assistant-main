import json
import logging
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.config import STUDY_COACH_PROMPT
from app.agent.state import AgentState
from app.agent.state.schema import AchievementSignal, ChatResponse
from app.rag import retrieve
from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# ── Achievement detection ──────────────────────────────────────────────────

_ACHIEVEMENT_SYSTEM = (
    "You are analyzing a Bible memorization coaching conversation.\n"
    "Decide whether the LAST EXCHANGE represents the **successful completion** of a memorization session.\n\n"
    "completed=true ONLY when ALL of these are true:\n"
    "1. The USER (not the coach) has actually typed out or quoted a verse or significant portion from memory\n"
    "2. The coach's reply explicitly CONFIRMS it was correct (e.g. 'well done', 'that's right', 'perfect', 'you got it')\n"
    "3. The session is wrapping up — the coach gives a spaced-repetition schedule, says 'you've memorized it', "
    "   or the user explicitly says 'I memorized it' / 'I got it'\n\n"
    "completed=false if:\n"
    "- The coach is still teaching, presenting chunks, or asking the user to try\n"
    "- The user has not yet quoted anything back from memory\n"
    "- This is the opening or middle of a session\n"
    "- There is any doubt — default to false\n\n"
    "If completed, extract:\n"
    "- topic: the verse reference(s) being memorized (e.g. 'John 3:16')\n"
    "- technique: the primary technique used (chunking / anchor word trail / vivid scene / "
    "  rhythm and cadence / first-letter prompt / association / spaced repetition / general)\n"
    "- summary: one short encouraging sentence describing the accomplishment "
    "  (start with the 🧠 emoji, mention the verse and technique)\n\n"
    "If NOT completed, set completed=false and leave the other fields empty."
)


class _CompletionCheck(AchievementSignal):
    """Extended schema used only for the LLM structured-output call."""

    completed: bool

    # Make the required AchievementSignal fields optional here
    topic: str = ""
    technique: str = ""
    summary: str = ""


def _detect_achievement(
    last_human: str,
    last_ai: str,
) -> Optional[AchievementSignal]:
    """Run a cheap structured-output check on the last exchange."""
    llm = get_llm(temperature=0)
    structured = llm.with_structured_output(_CompletionCheck)
    excerpt = f"USER: {last_human}\n\nASSISTANT (coach reply): {last_ai}"
    try:
        result: _CompletionCheck = structured.invoke(
            [
                {"role": "system", "content": _ACHIEVEMENT_SYSTEM},
                {"role": "user", "content": excerpt},
            ]
        )
        logger.info(
            "[study_coach] achievement check → completed=%s topic=%r technique=%r",
            result.completed,
            result.topic,
            result.technique,
        )
        if result.completed and result.topic:
            return AchievementSignal(
                topic=result.topic,
                technique=result.technique or "general",
                summary=result.summary or f"🧠 Memorized {result.topic}",
            )
    except Exception as exc:
        logger.warning("[study_coach] achievement detection failed: %s", exc)
    return None


# ── Main node ──────────────────────────────────────────────────────────────


def call_study_coach_model(state: AgentState) -> AgentState:
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    query = user_messages[-1].content if user_messages else ""

    logger.info("[study_coach] RAG query: %r", query)

    exact_docs, semantic_docs = retrieve(query, translation=state.get("translation"))

    logger.info(
        "[study_coach] Exact: [%s] | Semantic: [%s]",
        ", ".join(d.metadata["reference"] for d in exact_docs),
        ", ".join(d.metadata["reference"] for d in semantic_docs),
    )

    context_parts: list[str] = []
    if exact_docs:
        context_parts.append(
            "EXACT MATCH — These verses were explicitly requested. You MUST use them:\n"
            + "\n".join(
                f"  {d.metadata['reference']}: {d.page_content}" for d in exact_docs
            )
        )
    if semantic_docs:
        context_parts.append(
            "ADDITIONAL CONTEXT — Related verses for background:\n"
            + "\n".join(
                f"  {d.metadata['reference']}: {d.page_content}" for d in semantic_docs
            )
        )

    context_block = (
        "\n\n".join(context_parts) if context_parts else "No verses retrieved."
    )

    translation_label = state.get("translation") or "ASV"
    augmented_prompt = (
        STUDY_COACH_PROMPT
        + f"\n\n--- RETRIEVED VERSES ({translation_label}) ---\n"
        + context_block
        + "\n--- END OF RETRIEVED VERSES ---"
    )

    llm = get_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(ChatResponse)
    messages = [SystemMessage(content=augmented_prompt)] + state["messages"]
    response: ChatResponse = structured_llm.invoke(messages)

    ai_content = json.dumps(response.model_dump())

    # --- Achievement detection (cheap secondary call) ---
    achievement = _detect_achievement(
        last_human=query,
        last_ai=response.text,
    )

    update: dict = {"messages": [AIMessage(content=ai_content)]}
    if achievement:
        update["achievement"] = achievement
    else:
        # Explicitly clear any previous achievement so it isn't re-consumed
        update["achievement"] = None

    return update
