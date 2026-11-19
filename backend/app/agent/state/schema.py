from typing import Annotated, Literal, Optional, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


class FlashCard(BaseModel):
    front: str
    back: str


class ChatResponse(BaseModel):
    type: Literal["text", "flashcard"]
    # Always present: the conversational message or caption above cards.
    text: str
    # Populated only when type="flashcard".
    cards: list[FlashCard] = []
    # Verse/chunk/passage text to display in a dedicated blurrable block.
    # Keep ALL verse content here, NOT inside 'text'.
    verse_display: str = ""
    # True when the coach has just asked the user to recite from memory.
    recite_mode: bool = False


class AchievementSignal(BaseModel):
    """Set by study_coach when it detects a memorization session completing."""
    topic: str           # verse(s) being memorized, e.g. "John 3:16"
    technique: str       # e.g. "chunking", "vivid scene", "first-letter prompt"
    summary: str         # one natural-language sentence about what happened


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    # Set by the router node; reclassified every turn
    route: str  # "bible_search" | "study_coach"
    # Set by study_coach when a session completes; cleared after being consumed
    achievement: Optional[AchievementSignal]
    # User's preferred Bible translation (e.g. "BSB", "eng_kjv"); defaults to ASV
    translation: Optional[str]
