import os

import psycopg
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver

from app.agent.nodes.router import router_node
from app.agent.nodes.bible_search import call_bible_search_model
from app.agent.nodes.study_coach import call_study_coach_model
from app.agent.state import AgentState

_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://study_user:study_pass@db:5432/study_db",
)


def _select_route(state: AgentState) -> str:
    return state.get("route", "bible_search")


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("router", router_node)
    graph.add_node("bible_search", call_bible_search_model)
    graph.add_node("study_coach", call_study_coach_model)

    graph.set_entry_point("router")

    graph.add_conditional_edges(
        "router",
        _select_route,
        {
            "bible_search": "bible_search",
            "study_coach": "study_coach",
        },
    )

    graph.add_edge("bible_search", END)
    graph.add_edge("study_coach", END)

    # Persistent connection — stays open for the lifetime of the process
    conn = psycopg.connect(_DB_URL, autocommit=True)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()  # Creates LangGraph checkpoint tables if they don't exist

    return graph.compile(checkpointer=checkpointer)


unified_graph = build_graph()
