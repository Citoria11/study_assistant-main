import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.graphs import mnemonics_graph
from app.database.models import Checkpointer
from app.database.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


class MnemonicsRequest(BaseModel):
    message: str
    thread_id: str


class MnemonicsResponse(BaseModel):
    response: str
    thread_id: str


@router.post("/invoke", response_model=MnemonicsResponse)
async def invoke_mnemonics(body: MnemonicsRequest, db: Session = Depends(get_db)):
    """
    Send a verse or passage to the mnemonics agent and receive
    tailored memory aids and study techniques.
    """
    config = {"configurable": {"thread_id": body.thread_id}}

    try:
        result = mnemonics_graph.invoke(
            {"messages": [HumanMessage(content=body.message)]},
            config=config,
        )
    except Exception as exc:
        logger.error("Mnemonics invocation failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    last_message = result["messages"][-1]
    response_text = (
        last_message.content if hasattr(last_message, "content") else str(last_message)
    )

    checkpoint = db.get(Checkpointer, body.thread_id)
    if checkpoint is None:
        checkpoint = Checkpointer(thread_id=body.thread_id)
        db.add(checkpoint)
    checkpoint.checkpoint_data = response_text
    db.commit()

    return MnemonicsResponse(response=response_text, thread_id=body.thread_id)
