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
    target_scope: "TargetScope"
    status: "TaskStatus"
    result_summary: str | None
    origin_step_id: int


ProductType = Literal["slide_infographic", "document_design", "comic"]
IntentType = Literal["new", "refine", "regenerate"]
TaskCapability = Literal["writer", "visualizer", "researcher", "data_analyst"]
TaskStatus = Literal["pending", "in_progress", "completed", "blocked"]
PlanPatchOpType = Literal["edit_pending", "split_pending", "append_tail"]


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
    target_scope: TargetScope
    status: TaskStatus
    result_summary: str | None
    retries_used: int


class PlanPatchOp(TypedDict):
    """Allowed patch operation against frozen plan."""
    op: PlanPatchOpType
    payload: dict[str, Any]
    target_step_id: NotRequired[int | None]


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
    summary: str | None  # Compact summary of older conversation
    # Orchestration fields
    product_type: NotRequired[ProductType]
    request_intent: NotRequired[IntentType]
    interrupt_intent: NotRequired[bool]
    target_scope: NotRequired[TargetScope]
    selected_image_inputs: NotRequired[list[dict[str, Any]]]
    attachments: NotRequired[list[dict[str, Any]]]
    pptx_context: NotRequired[dict[str, Any]]
    pptx_template_base64: NotRequired[str]
    aspect_ratio: NotRequired[str]
    plan_status: NotRequired[Literal["frozen"]]
    plan_baseline_hash: NotRequired[str]
    plan_patch_log: NotRequired[list[PlanPatchOp]]
    rethink_used_turn: NotRequired[int]
    rethink_used_by_step: NotRequired[dict[int, int]]
    task_board: NotRequired[TaskBoard]
    artifact_graph: NotRequired[list[ArtifactDependencyEdge]]
    quality_reports: NotRequired[dict[int, QualityReport]]
    asset_unit_ledger: NotRequired[dict[str, AssetUnitLedgerEntry]]


class ResearchSubgraphState(State):
    """Private state for the Researcher Subgraph."""
    internal_research_tasks: list[ResearchTask]
    # [New] Stores intermediate parallel results before aggregation
    internal_research_results: Annotated[list[ResearchResult], merge_research_results]
    is_decomposed: bool
    current_task_index: int  # [Added] To track sequential execution
