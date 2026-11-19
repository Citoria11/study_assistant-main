from langgraph.graph import StateGraph, END

from app.agent.nodes.bible_search import call_bible_search_model
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_bible_search_model)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile()


agent_graph = build_graph()
