import json
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.agent.graphs import unified_graph as agent_graph
from app.database.models import Checkpointer, User
from app.database.session import get_db
from app.routes.auth import decode_token

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class InvokeRequest(BaseModel):
    message: str
    thread_id: str
    token: str | None = None  # optional auth token to load user's translation


class CardData(BaseModel):
    front: str
    back: str


class InvokeResponse(BaseModel):
    type: str  # "text" | "flashcard"
    text: str  # always present: conversational message / caption
    cards: list[CardData] = []
    verse_display: str = ""  # verse/chunk content to show in blurrable block
    recite_mode: bool = False  # True when coach asks user to recite
    thread_id: str
    achievement: dict | None = None  # set when study_coach detects session completion
    route: str = "bible_search"  # "bible_search" | "study_coach"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/invoke", response_model=InvokeResponse)
async def invoke_agent(body: InvokeRequest, db: Session = Depends(get_db)):
    """
    Send a message to the LangGraph agent and receive a response.

    The `thread_id` allows the agent to maintain conversation history
    across multiple invocations (checkpointing).
    """
    config = {"configurable": {"thread_id": body.thread_id}}

    # Look up user's preferred translation if a token is provided
    translation: str | None = None
    if body.token:
        try:
            payload = decode_token(body.token)
            user = db.get(User, payload.get("sub"))
            if user:
                translation = user.preferred_translation or None
        except Exception:
            pass  # bad token — fall back to default translation

    try:
        result = agent_graph.invoke(
            {"messages": [HumanMessage(content=body.message)], "translation": translation},
            config=config,
        )
    except Exception as exc:
        logger.error("Agent invocation failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Extract achievement signal if study_coach set one
    raw_achievement = result.get("achievement")
    achievement_dict = None
    if raw_achievement is not None:
        try:
            achievement_dict = raw_achievement.model_dump()
        except AttributeError:
            achievement_dict = dict(raw_achievement) if raw_achievement else None
        logger.info("[invoke] achievement detected: %s", achievement_dict)

    # Extract the last AI message from the result
    last_message = result["messages"][-1]
    raw_content = (
        last_message.content if hasattr(last_message, "content") else str(last_message)
    )

    # Parse structured JSON response from the node; fall back to plain text.
    logger.info("Agent raw_content: %s", raw_content[:600])
    try:
        parsed = json.loads(raw_content)
        resp_type = parsed.get("type", "text")
        resp_text = parsed.get("text", raw_content)
        resp_cards = [CardData(**c) for c in parsed.get("cards", [])]
        resp_verse_display = parsed.get("verse_display", "")
        resp_recite_mode = parsed.get("recite_mode", False)
    except (json.JSONDecodeError, TypeError, ValueError):
        resp_type = "text"
        resp_text = raw_content
        resp_cards = []
        resp_verse_display = ""
        resp_recite_mode = False

    # Persist / update checkpoint record in the database
    checkpoint = db.get(Checkpointer, body.thread_id)
    if checkpoint is None:
        checkpoint = Checkpointer(thread_id=body.thread_id)
        db.add(checkpoint)
    checkpoint.checkpoint_data = raw_content
    db.commit()

    route = result.get("route", "bible_search") or "bible_search"

    return InvokeResponse(
        type=resp_type, text=resp_text, cards=resp_cards,
        verse_display=resp_verse_display, recite_mode=resp_recite_mode,
        thread_id=body.thread_id, achievement=achievement_dict, route=route
    )


@router.get("/history/{thread_id}")
async def get_history(thread_id: str):
    """
    Return the display-ready message history for a thread by reading
    directly from the LangGraph checkpoint state.
    """
    config = {"configurable": {"thread_id": thread_id}}
    try:
        snapshot = agent_graph.get_state(config)
    except Exception as exc:
        logger.error("get_state failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not snapshot or not snapshot.values:
        return {"messages": []}

    result = []
    for msg in snapshot.values.get("messages", []):
        if isinstance(msg, HumanMessage):
            result.append({"role": "user", "content": msg.content, "type": "text", "cards": []})
        elif isinstance(msg, AIMessage):
            try:
                parsed = json.loads(msg.content)
                result.append({
                    "role": "assistant",
                    "type": parsed.get("type", "text"),
                    "content": parsed.get("text", msg.content),
                    "cards": parsed.get("cards", []),
                })
            except (json.JSONDecodeError, TypeError):
                result.append({"role": "assistant", "content": msg.content, "type": "text", "cards": []})

    return {"messages": result}


@router.delete("/checkpointer/{thread_id}", status_code=204)
async def delete_checkpointer(thread_id: str, db: Session = Depends(get_db)):
    """
    Delete the checkpointer for a given thread.

    This effectively resets the conversation history for that thread,
    which is useful for debugging or when a conversation gets into a
    bad state.
    """
    checkpoint = db.get(Checkpointer, thread_id)
    if checkpoint:
        db.delete(checkpoint)
        db.commit()
    # Return 204 regardless (idempotent delete)
