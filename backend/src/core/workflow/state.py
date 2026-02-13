from typing import Literal, TypedDict, Any, Annotated, NotRequired
from langgraph.graph import MessagesState

from src.shared.schemas.outputs import ResearchTask, ResearchResult


class TaskStep(TypedDict, total=False):
    """A single step in the execution plan."""
    id: int
    capability: "TaskCapability"
    mode: str  # Capability-specific execution mode
    instruction: str
    title: str
    description: str
    design_direction: str | None
    inputs: list[str]
    outputs: list[str]
    preconditions: list[str]
    validation: list[str]
    success_criteria: list[str]
    fallback: list[str]
    depends_on: list[int]
    asset_requirements: list["AssetRequirement"]
    target_scope: "TargetScope"
    status: "TaskStatus"
    result_summary: str | None
    origin_step_id: int


ProductType = Literal["slide", "design", "comic"]
IntentType = Literal["new", "refine", "regenerate"]
PlanningMode = Literal["create", "update"]
TaskCapability = Literal["writer", "visualizer", "researcher", "data_analyst"]
TaskStatus = Literal["pending", "in_progress", "completed", "blocked"]


class TargetScope(TypedDict, total=False):
    """Scope for partial modifications."""
    asset_unit_ids: list[str]
    asset_units: list[dict[str, Any]]
    slide_numbers: list[int]
    page_numbers: list[int]
    panel_numbers: list[int]
    character_ids: list[str]
    artifact_ids: list[str]


class OrchestrationTaskStep(TypedDict, total=False):
    """Task card used by the frozen-plan orchestrator."""
    id: int
    capability: TaskCapability
    mode: str
    instruction: str
    title: str
    description: str
    inputs: list[str]
    success_criteria: list[str]
    asset_requirements: list["AssetRequirement"]
    target_scope: TargetScope
    status: TaskStatus
    result_summary: str | None
    retries_used: int


class TaskBoard(TypedDict):
    """Execution board grouped by status."""
    pending: list[int]
    in_progress: list[int]
    completed: list[int]
    blocked: list[int]


class ArtifactDependencyEdge(TypedDict):
    """DAG edge between artifacts."""
    from_artifact_id: str
    to_artifact_id: str


class QualityReport(TypedDict, total=False):
    """Per-step quality evaluation result."""
    step_id: int
    passed: bool
    score: float | None
    failed_checks: list[str]
    notes: str | None


class AssetRequirement(TypedDict, total=False):
    """Planner-declared abstract asset requirement."""
    role: str
    required: bool
    scope: Literal["global", "per_unit"]
    mime_allow: list[str]
    source_preference: list[str]
    max_items: int
    instruction: str | None


class AssetBinding(TypedDict, total=False):
    """Resolved binding from requirement role to concrete asset IDs."""
    role: str
    asset_ids: list[str]
    reason: str | None


class AssetUnitLedgerEntry(TypedDict, total=False):
    """Persistent mapping for the minimum editable unit (single image)."""
    unit_id: str
    unit_kind: str
    unit_index: int | None
    artifact_id: str
    image_url: str | None
    producer_step_id: int | None
    title: str | None


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
    # Orchestration fields
    product_type: NotRequired[ProductType]
    request_intent: NotRequired[IntentType]
    planning_mode: NotRequired[PlanningMode]
    interrupt_intent: NotRequired[bool]
    target_scope: NotRequired[TargetScope]
    selected_image_inputs: NotRequired[list[dict[str, Any]]]
    attachments: NotRequired[list[dict[str, Any]]]
    pptx_context: NotRequired[dict[str, Any]]
    aspect_ratio: NotRequired[str]
    coordinator_followup_options: NotRequired[list[dict[str, str]]]
    quality_reports: NotRequired[dict[int, QualityReport]]
    asset_unit_ledger: NotRequired[dict[str, AssetUnitLedgerEntry]]
    # Asset state (single-turn scope)
    asset_catalog: NotRequired[dict[str, dict[str, Any]]]  # all known assets keyed by asset_id
    candidate_assets_by_step: NotRequired[dict[str, list[str]]]  # per-step candidate asset ids
    selected_assets_by_step: NotRequired[dict[str, list[str]]]
    asset_bindings_by_step: NotRequired[dict[str, list[AssetBinding]]]


class ResearchSubgraphState(State):
    """Private state for the Researcher Subgraph."""
    internal_research_tasks: list[ResearchTask]
    # [New] Stores intermediate parallel results before aggregation
    internal_research_results: Annotated[list[ResearchResult], merge_research_results]
    is_decomposed: bool
    current_task_index: int  # [Added] To track sequential execution
