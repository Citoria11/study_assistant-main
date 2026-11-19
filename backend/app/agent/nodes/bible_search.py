import json
import logging

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.config import BIBLE_SEARCH_PROMPT
from app.agent.state import AgentState
from app.agent.state.schema import ChatResponse
from app.rag import retrieve
from app.services.llm import get_llm

logger = logging.getLogger(__name__)


def call_bible_search_model(state: AgentState) -> AgentState:
    # Retrieve relevant verses based on the latest user message
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    query = user_messages[-1].content if user_messages else ""

    logger.info("[bible_search] RAG query: %r", query)

    exact_docs, semantic_docs = retrieve(query, translation=state.get("translation"))

    logger.info(
        "[bible_search] Exact: [%s] | Semantic: [%s]",
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

    augmented_prompt = (
        BIBLE_SEARCH_PROMPT
        + "\n\n--- RETRIEVED VERSES ---\n"
        + context_block
        + "\n--- END OF RETRIEVED VERSES ---"
    )

    llm = get_llm(temperature=0.2)
    structured_llm = llm.with_structured_output(ChatResponse)
    messages = [SystemMessage(content=augmented_prompt)] + state["messages"]
    response: ChatResponse = structured_llm.invoke(messages)
    return {"messages": [AIMessage(content=json.dumps(response.model_dump()))]}
