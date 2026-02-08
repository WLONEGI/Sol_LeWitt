import json
import re
from typing import Any, TypeVar
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from src.shared.config.settings import settings
from src.core.workflow.state import State

T = TypeVar("T", bound=BaseModel)


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
