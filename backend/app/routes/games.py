import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent.graphs import game_generator_graph

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateGameRequest(BaseModel):
    game_type: str = Field(..., description="'memorama' or 'trivia'")
    focus: str = Field(
        ..., description="Topic, book, chapter range, or theme to focus on"
    )
    count: int = Field(
        default=8, ge=2, le=15, description="Number of pairs or questions"
    )


@router.post("/generate")
async def generate_game(body: GenerateGameRequest):
    if body.game_type not in ("memorama", "trivia"):
        raise HTTPException(
            status_code=400,
            detail="game_type must be 'memorama' or 'trivia'",
        )

    logger.info(
        "Generating %s game | focus=%r | count=%d",
        body.game_type,
        body.focus,
        body.count,
    )

    result = await game_generator_graph.ainvoke(
        {
            "game_type": body.game_type,
            "focus": body.focus,
            "count": body.count,
            "result": None,
        }
    )

    return result["result"]
