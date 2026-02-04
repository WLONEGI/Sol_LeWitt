import re
from typing import Any, TypeVar
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from src.shared.config.settings import settings
from src.core.workflow.state import State

T = TypeVar("T", bound=BaseModel)

def _update_artifact(state: State, key: str, value: Any) -> dict[str, Any]:
    """Helper to update artifacts dictionary."""
    artifacts = state.get("artifacts", {})
    if artifacts is None:
        artifacts = {}
    artifacts[key] = value
    return artifacts

def _extract_first_json(text: str) -> str | None:
    """Extract first JSON object from text."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None

async def run_structured_output(
    llm,
    schema: type[T],
    messages: list,
    config: dict,
    repair_hint: str
) -> T:
    """Structured output with fallback JSON repair."""
    try:
        structured_llm = llm.with_structured_output(schema)
        return await structured_llm.ainvoke(messages, config=config)
    except Exception as first_error:
        repair_messages = list(messages)
        repair_messages.append(
            HumanMessage(
                content=(
                    "Return ONLY valid JSON for the schema. "
                    f"{repair_hint}"
                )
            )
        )
        raw = await llm.ainvoke(repair_messages, config=config)
        raw_text = raw.content if hasattr(raw, "content") else str(raw)
        json_text = _extract_first_json(raw_text)
        if not json_text:
            raise first_error
        return schema.model_validate_json(json_text)

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
    goto: str = "supervisor"
) -> Command:
    """
    Common helper to generate the Command response for worker nodes.
    Ensures consistent AIMessage usage and artifact updates.
    """
    
    # 1. Main Response (Raw Content for Context)
    # Using generic response format from settings
    response_content = settings.RESPONSE_FORMAT.format(role=role, content=content_json)
    main_message = AIMessage(
        content=response_content, 
        name=role
    )

    # 2. Worker Result UI Message
    status_label = "completed" if not is_error else "error"
    
    result_message = AIMessage(
        content=result_summary if result_summary else f"{role.capitalize()} finished.",
        additional_kwargs={
            "ui_type": "worker_result", 
            "role": role, 
            "status": status_label,
            "result_summary": result_summary
        }, 
        name=f"{role}_ui"
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
        name=f"{role}_artifact"
    )

    # Update State: Artifacts
    # Note: State updates in Command are merged.
    updated_artifacts = _update_artifact(state, artifact_id, content_json)
    
    return Command(
        update={
            "messages": [main_message, result_message, artifact_message],
            "artifacts": updated_artifacts,
            "plan": state["plan"]
        },
        goto=goto,
    )
