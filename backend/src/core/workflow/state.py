from typing import Literal, TypedDict, Any, Annotated
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


def merge_artifacts(
    old: dict[str, Any] | None,
    new: dict[str, Any] | None
) -> dict[str, Any]:
    """Merge artifacts but allow deletions with value=None."""
    result = dict(old or {})
    if not new:
        return result
    for key, value in new.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = value
    return result


def merge_research_results(
    old: list[ResearchResult] | None,
    new: list[ResearchResult] | None
) -> list[ResearchResult]:
    """Append results, but treat [] as explicit clear."""
    if new is None:
        return list(old or [])
    if new == []:
        return []
    return list(old or []) + list(new)


class State(MessagesState):
    """State for the agent system, extends MessagesState."""

    # Runtime Variables
    plan: list[TaskStep]
    artifacts: Annotated[dict[str, Any], merge_artifacts]  # Store outputs from workers (text, charts, etc.)
    summary: str | None  # Compact summary of older conversation


class ResearchSubgraphState(State):
    """Private state for the Researcher Subgraph."""
    internal_research_tasks: list[ResearchTask]
    # [New] Stores intermediate parallel results before aggregation
    internal_research_results: Annotated[list[ResearchResult], merge_research_results]
    is_decomposed: bool
    current_task_index: int  # [Added] To track sequential execution
