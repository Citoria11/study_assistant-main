import logging
import os
from typing import Optional

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

from app.services.llm import get_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class GameGeneratorState(TypedDict):
    game_type: str  # "memorama" | "trivia"
    focus: str  # e.g. "Psalms 1-30", "the life of Paul"
    count: int  # number of pairs / questions
    result: Optional[dict]  # populated by the generate node


# ---------------------------------------------------------------------------
# Pydantic output schemas
# ---------------------------------------------------------------------------


class MemoramaPair(BaseModel):
    id: int = Field(description="Sequential integer starting at 1")
    reference: str = Field(description="Bible verse reference, e.g. 'John 3:16'")
    text: str = Field(description="Full text of the verse (NIV translation preferred)")


class MemoramaGame(BaseModel):
    pairs: list[MemoramaPair] = Field(description="List of verse reference/text pairs")


class TriviaQuestion(BaseModel):
    id: int = Field(description="Sequential integer starting at 1")
    question: str = Field(description="The trivia question")
    options: list[str] = Field(description="Exactly 4 answer choices")
    answer: str = Field(
        description="The correct answer — must match one of the options exactly"
    )
    explanation: str = Field(
        description="Brief explanation with Bible reference (book + chapter)"
    )


class TriviaGame(BaseModel):
    questions: list[TriviaQuestion] = Field(description="List of trivia questions")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_MEMORAMA_PROMPT = """\
You are a Bible verse expert. Generate exactly {count} unique verse pairs for a Memorama \
(memory matching card game).

Focus area: {focus}

Rules:
- Draw primarily from the Focus area.
- IMPORTANT: If the focus area is narrow (e.g. a single verse or just a few verses), \
you MUST expand to the surrounding chapter(s) or closely related passages in the same book \
to reach exactly {count} unique pairs. Never return fewer than {count} pairs.
- Each pair has:
    "reference": the verse reference (e.g. "John 3:16")
    "text": the complete verse text in NIV translation
- Verify that each reference and text are correctly matched.
- Use variety — different verses and themes when possible.
- Avoid duplicate references.
- Do NOT paraphrase or abbreviate the verse text.
"""

_TRIVIA_PROMPT = """\
You are a Bible knowledge expert. Generate exactly {count} multiple-choice trivia questions.

Focus area: {focus}

Rules:
- Draw primarily from the Focus area.
- IMPORTANT: If the focus area is narrow (e.g. a single verse or a few verses), \
you MUST expand to cover the surrounding chapter(s) or related themes in the same book \
to reach exactly {count} questions. Never return fewer than {count} questions.
- Each question has exactly 4 answer options (no more, no less).
- The "answer" field must be a word-for-word match of one of the options.
- Include a brief "explanation" citing the relevant Bible book and chapter.
- Vary difficulty: some easy, some moderate, some hard.
- Topics may include events, people, places, numbers, prophecies, and teachings.
- All facts must be scripturally accurate.
"""


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


def generate_game_node(state: GameGeneratorState) -> dict:
    game_type = state["game_type"]
    focus = state["focus"]
    count = state["count"]

    llm = get_llm(temperature=0.7)

    if game_type == "memorama":
        structured_llm = llm.with_structured_output(MemoramaGame)
        prompt = _MEMORAMA_PROMPT.format(count=count, focus=focus)
        result: MemoramaGame = structured_llm.invoke(prompt)
        return {"result": result.model_dump()}
    else:
        structured_llm = llm.with_structured_output(TriviaGame)
        prompt = _TRIVIA_PROMPT.format(count=count, focus=focus)
        result: TriviaGame = structured_llm.invoke(prompt)
        return {"result": result.model_dump()}


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def _build() -> object:
    g = StateGraph(GameGeneratorState)
    g.add_node("generate", generate_game_node)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    return g.compile()


game_generator_graph = _build()
