import json
import re
from typing import Any, TypeVar
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from src.shared.config.settings import settings
from src.core.workflow.state import State

T = TypeVar("T", bound=BaseModel)
ARTIFACT_STEP_ID_PATTERN = re.compile(r"step_(\d+)_")
RESEARCH_INPUT_KEYWORDS = (
    "research",
    "調査",
    "出典",
    "根拠",
    "reference",
    "citation",
    "source",
    "画像検索",
    "image search",
)


def _normalize_worker_capability(value: str | None) -> str:
    if not isinstance(value, str):
        return "worker"
    lowered = value.strip().lower()
    if lowered in {"writer", "researcher", "visualizer", "data_analyst"}:
        return lowered
    return "worker"

def _update_artifact(state: State, key: str, value: Any) -> dict[str, Any]:
    """Helper to update artifacts dictionary."""
    artifacts = state.get("artifacts", {})
    if artifacts is None:
        artifacts = {}
    artifacts[key] = value
    return artifacts

def extract_first_json(text: str) -> str | None:
    """Extract first JSON object from text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None

def split_content_parts(content: Any) -> tuple[str, str]:
    """Split content into (thinking_text, normal_text)."""
    thinking_parts: list[str] = []
    text_parts: list[str] = []

    def _add(parts: list[str], value: Any) -> None:
        if isinstance(value, str):
            parts.append(value)

    if isinstance(content, str):
        _add(text_parts, content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                part_text = part.get("text")
                if part_type == "thinking":
                    _add(thinking_parts, part_text)
                else:
                    _add(text_parts, part_text)
            else:
                _add(text_parts, part)
    elif isinstance(content, dict):
        part_type = content.get("type")
        part_text = content.get("text")
        if part_type == "thinking":
            _add(thinking_parts, part_text)
        else:
            _add(text_parts, part_text)

    return ("".join(thinking_parts), "".join(text_parts))


def _parse_json_if_possible(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _extract_step_id_from_artifact_id(artifact_id: str) -> int | None:
    match = ARTIFACT_STEP_ID_PATTERN.search(artifact_id)
    if not match:
        return None
    return int(match.group(1))


def _trim_text(value: Any, max_chars: int = 3000) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars]}...(truncated)"


def _compact_research_content(content: Any) -> Any:
    if not isinstance(content, dict):
        return _trim_text(content, max_chars=1200) or content

    compact: dict[str, Any] = {}
    for key in ("task_id", "perspective", "search_mode", "summary", "total_tasks", "completed_tasks", "failed_tasks", "confidence"):
        if key in content:
            compact[key] = content[key]

    report = _trim_text(content.get("report"), max_chars=2500)
    if report:
        compact["report"] = report

    sources = content.get("sources")
    if isinstance(sources, list):
        compact["sources"] = [str(item) for item in sources[:12]]

    def _pick_image_fields(items: Any) -> list[dict[str, Any]]:
        picked: list[dict[str, Any]] = []
        if not isinstance(items, list):
            return picked
        for item in items[:10]:
            if not isinstance(item, dict):
                continue
            picked.append(
                {
                    "image_url": item.get("image_url"),
                    "source_url": item.get("source_url"),
                    "gcs_url": item.get("gcs_url"),
                    "caption": item.get("caption"),
                    "license_note": item.get("license_note"),
                }
            )
        return picked

    image_candidates = _pick_image_fields(content.get("image_candidates"))
    if image_candidates:
        compact["image_candidates"] = image_candidates

    stored_images = _pick_image_fields(content.get("stored_images"))
    if stored_images:
        compact["stored_images"] = stored_images

    return compact


def _normalize_depends_on(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    depends_on: list[int] = []
    for item in value:
        if isinstance(item, int) and item > 0 and item not in depends_on:
            depends_on.append(item)
    return depends_on


def _collect_artifacts_by_step(artifacts: dict[str, Any]) -> dict[int, list[tuple[str, Any]]]:
    by_step: dict[int, list[tuple[str, Any]]] = {}
    for artifact_id, payload in artifacts.items():
        if not isinstance(artifact_id, str):
            continue
        step_id = _extract_step_id_from_artifact_id(artifact_id)
        if step_id is None:
            continue
        by_step.setdefault(step_id, []).append((artifact_id, payload))
    return by_step


def resolve_step_dependency_context(state: State, current_step: dict[str, Any]) -> dict[str, Any]:
    """
    Resolve planner-declared dependencies to concrete artifact payloads.
    Used by workers to read upstream outputs (especially researcher results).
    """
    plan = state.get("plan") or []
    artifacts = state.get("artifacts") or {}
    plan_by_id: dict[int, dict[str, Any]] = {}
    for step in plan:
        if isinstance(step, dict):
            step_id = step.get("id")
            if isinstance(step_id, int):
                plan_by_id[step_id] = step

    planned_inputs = [str(item) for item in (current_step.get("inputs") or []) if isinstance(item, str)]
    depends_on_ids = _normalize_depends_on(current_step.get("depends_on"))
    artifacts_by_step = _collect_artifacts_by_step(artifacts if isinstance(artifacts, dict) else {})

    dependency_artifacts: list[dict[str, Any]] = []

    def _append_step_artifacts(step_id: int) -> None:
        producer_step = plan_by_id.get(step_id, {})
        producer_capability = _normalize_worker_capability(producer_step.get("capability"))
        producer_mode = str(producer_step.get("mode") or "")
        producer_title = str(producer_step.get("title") or producer_step.get("description") or "")
        for artifact_id, raw_payload in sorted(artifacts_by_step.get(step_id, []), key=lambda item: item[0]):
            parsed_payload = _parse_json_if_possible(raw_payload)
            content = (
                _compact_research_content(parsed_payload)
                if producer_capability == "researcher"
                else parsed_payload
            )
            dependency_artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "producer_step_id": step_id,
                    "producer_capability": producer_capability,
                    "producer_mode": producer_mode,
                    "producer_title": producer_title,
                    "content": content,
                }
            )

    for step_id in depends_on_ids:
        _append_step_artifacts(step_id)

    # Fallback: planner inputs mention research but explicit depends_on is missing.
    if not any(item.get("producer_capability") == "researcher" for item in dependency_artifacts):
        merged_inputs = " ".join(planned_inputs).lower()
        requires_research = any(keyword in merged_inputs for keyword in RESEARCH_INPUT_KEYWORDS)
        if requires_research:
            candidate_research_steps: list[int] = []
            for step_id, step in plan_by_id.items():
                if _normalize_worker_capability(step.get("capability")) == "researcher":
                    candidate_research_steps.append(step_id)
            for step_id in sorted(candidate_research_steps):
                _append_step_artifacts(step_id)

    resolved_research_inputs = [
        item
        for item in dependency_artifacts
        if item.get("producer_capability") == "researcher"
    ]

    return {
        "planned_inputs": planned_inputs,
        "depends_on_step_ids": depends_on_ids,
        "resolved_dependency_artifacts": dependency_artifacts,
        "resolved_research_inputs": resolved_research_inputs,
    }


def build_worker_error_payload(
    *,
    error_text: str,
    failed_checks: list[str] | None = None,
    notes: str | None = None,
) -> str:
    payload = {
        "error": error_text,
        "failed_checks": failed_checks or ["worker_execution"],
        "notes": notes or error_text,
    }
    return json.dumps(payload, ensure_ascii=False)

async def run_structured_output(
    llm,
    schema: type[T],
    messages: list,
    config: dict,
    repair_hint: str,
    max_retries: int = 2,
) -> T:
    """Run strict structured output with retriable with_structured_output calls."""
    attempt = 0
    current_messages = list(messages)
    last_error: Exception | None = None

    while attempt <= max_retries:
        try:
            structured_llm = llm.with_structured_output(schema)
            return await structured_llm.ainvoke(current_messages, config=config)
        except Exception as e:
            last_error = e
            if attempt >= max_retries:
                break
            current_messages = list(messages) + [
                HumanMessage(
                    content=(
                        "Return ONLY valid JSON matching the schema. "
                        f"{repair_hint} Retry attempt {attempt + 1}/{max_retries}."
                    )
                )
            ]
            attempt += 1

    if last_error is not None:
        raise last_error
    raise RuntimeError("run_structured_output failed without explicit error")

def create_worker_response(
    role: str,
    content_json: str,
    result_summary: str,
    current_step_id: str | int,
    state: State,
    artifact_key_suffix: str,
    artifact_title: str = "Artifact",
    artifact_icon: str = "FileText",
    artifact_preview_urls: list[str] | None = None,
    is_error: bool = False,
    goto: str = "supervisor",
    extra_update: dict[str, Any] | None = None,
    capability: str | None = None,
    emitter_name: str | None = None,
) -> Command:
    """
    Common helper to generate the Command response for worker nodes.
    Ensures consistent AIMessage usage and artifact updates.
    """
    
    # 1. Main Response (Raw Content for Context)
    # Using generic response format from settings
    worker_capability = _normalize_worker_capability(capability or role)
    message_name = emitter_name or role

    response_content = settings.RESPONSE_FORMAT.format(role=worker_capability, content=content_json)
    main_message = AIMessage(
        content=response_content, 
        name=message_name
    )

    # 2. Worker Result UI Message
    status_label = "completed" if not is_error else "error"
    
    result_message = AIMessage(
        content=result_summary if result_summary else f"{role.capitalize()} finished.",
        additional_kwargs={
            "ui_type": "worker_result", 
            "capability": worker_capability,
            "status": status_label,
            "result_summary": result_summary
        }, 
        name=f"{message_name}_ui"
    )

    # 3. Artifact UI Message
    # Standardize artifact ID generation
    artifact_id = f"step_{current_step_id}_{artifact_key_suffix}"
    
    # Prepare artifact button data
    artifact_kwargs = {
        "ui_type": "artifact_view",
        "artifact_id": artifact_id,
        "title": artifact_title if not is_error else f"{artifact_title} (Failed)",
        "icon": artifact_icon
    }
    
    if artifact_preview_urls:
         artifact_kwargs["preview_urls"] = artifact_preview_urls
    
    # Use appropriate icon for error
    if is_error:
        artifact_kwargs["icon"] = "AlertTriangle"

    artifact_message = AIMessage(
        content=artifact_title,
        additional_kwargs=artifact_kwargs,
        name=f"{message_name}_artifact"
    )

    # Update State: Artifacts
    # Note: State updates in Command are merged.
    updated_artifacts = _update_artifact(state, artifact_id, content_json)
    
    update_payload: dict[str, Any] = {
        "messages": [main_message, result_message, artifact_message],
        "artifacts": updated_artifacts,
        "plan": state["plan"],
    }
    if isinstance(extra_update, dict):
        update_payload.update(extra_update)

    return Command(
        update=update_payload,
        goto=goto,
    )
