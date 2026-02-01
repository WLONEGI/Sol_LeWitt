from langgraph.graph import StateGraph, START
from langgraph.checkpoint.memory import MemorySaver

from src.core.workflow.state import State
from src.core.workflow.nodes import (
    supervisor_node,
    build_researcher_subgraph,
    coordinator_node,
    storywriter_node,
    visualizer_node,
    planner_node,
    data_analyst_node,
    # reviewer_node removed - Workers now have Self-Critique
)


def build_graph(checkpointer=None):
    """Build and return the agent workflow graph.
    
    Args:
        checkpointer: Optional persistence checkpointer (e.g. MemorySaver, AsyncPostgresSaver)
    """
    builder = StateGraph(State)
    builder.add_edge(START, "coordinator")
    builder.add_node("coordinator", coordinator_node)
    builder.add_node("planner", planner_node)
    builder.add_node("supervisor", supervisor_node)
    
    # === Researcher Subgraph ===
    researcher_app = build_researcher_subgraph()
    builder.add_node("researcher", researcher_app)
    # Researcher routes to Supervisor after completion (Reviewer removed)
    builder.add_edge("researcher", "supervisor") 

    builder.add_node("storywriter", storywriter_node)
    builder.add_node("visualizer", visualizer_node)
    builder.add_node("data_analyst", data_analyst_node)
    # reviewer_node removed - Workers now have Self-Critique

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_after=["planner"]
    )

