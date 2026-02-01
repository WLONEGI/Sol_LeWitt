from typing import Literal, TypedDict, Any, List, Annotated
import operator
from langgraph.graph import MessagesState

from src.shared.schemas.outputs import ResearchTask, ResearchResult


class TaskStep(TypedDict):
    """A single step in the execution plan."""
    id: int
    role: str  # The worker to execute this step (e.g., 'storywriter', 'coder')
    instruction: str  # Specific instruction for the worker
    description: str  # Brief description of the step
    status: Literal["pending", "in_progress", "complete"]  # Status of the step
    result_summary: str | None  # Summary of the execution result


class State(MessagesState):
    """State for the agent system, extends MessagesState."""

    # Runtime Variables
    plan: list[TaskStep]
    artifacts: dict[str, Any]  # Store outputs from workers (text, charts, etc.)


class ResearchSubgraphState(State):
    """Private state for the Researcher Subgraph."""
    internal_research_tasks: list[ResearchTask]
    # [New] Stores intermediate parallel results before aggregation
    internal_research_results: Annotated[list[ResearchResult], operator.add]
    is_decomposed: bool
