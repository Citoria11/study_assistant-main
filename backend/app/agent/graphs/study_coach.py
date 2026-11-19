from langgraph.graph import StateGraph, END

from app.agent.nodes.study_coach import call_study_coach_model
from app.agent.state import AgentState


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("agent", call_study_coach_model)
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)
    return graph.compile()


mnemonics_graph = build_graph()
