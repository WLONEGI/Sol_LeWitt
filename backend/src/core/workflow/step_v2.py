from __future__ import annotations

from typing import Any

from src.core.workflow.state import TaskCapability, TaskStatus


VALID_CAPABILITIES: set[str] = {"writer", "researcher", "visualizer", "data_analyst"}
VALID_STATUSES: set[str] = {"pending", "in_progress", "completed", "blocked"}


def destination_for_capability(capability: str | None) -> str:
    if isinstance(capability, str) and capability in VALID_CAPABILITIES:
        return capability
    return "writer"


def capability_from_any(step: dict[str, Any], fallback: str = "writer") -> TaskCapability:
    capability = step.get("capability")
    if isinstance(capability, str) and capability in VALID_CAPABILITIES:
        return capability  # type: ignore[return-value]

    return fallback if fallback in VALID_CAPABILITIES else "writer"  # type: ignore[return-value]


def default_mode_for_capability(
    capability: str,
    product_type: str | None,
    text: str = "",
) -> str:
    lowered = text.lower()
    if capability == "writer":
        if product_type == "comic":
            return "comic_script"
        if product_type == "design":
            return "document_blueprint"
        return "slide_outline"
    if capability == "visualizer":
        if product_type == "comic":
            return "comic_page_render"
        if product_type == "design":
            return "document_layout_render"
        return "slide_render"
    if capability == "researcher":
        return "text_search"
    if capability == "data_analyst":
        return "python_pipeline"
    return "generic"


def _normalize_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if not trimmed:
            continue
        out.append(trimmed)
    return out


def _normalize_depends_on(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        if not isinstance(item, int):
            continue
        if item <= 0:
            continue
        if item not in out:
            out.append(item)
    return out


def normalize_step_v2(
    raw_step: dict[str, Any],
    *,
    product_type: str | None,
    fallback_capability: str = "writer",
    fallback_instruction: str = "追加作業を実行する",
    fallback_title: str = "タスク",
) -> dict[str, Any]:
    """Normalize to the canonical V2 plan-step shape.

    Canonical keys:
    id, capability, mode, instruction, title, description,
    inputs, outputs, preconditions, validation, success_criteria,
    fallback, depends_on, target_scope, design_direction,
    status, result_summary.
    """
    step = dict(raw_step or {})

    capability = capability_from_any(step, fallback=fallback_capability)

    instruction = (
        _normalize_string(step.get("instruction"))
        or _normalize_string(fallback_instruction)
        or "追加作業を実行する"
    )
    title = (
        _normalize_string(step.get("title"))
        or _normalize_string(step.get("description"))
        or _normalize_string(fallback_title)
        or "タスク"
    )
    description = _normalize_string(step.get("description")) or title

    mode = _normalize_string(step.get("mode")) or default_mode_for_capability(
        capability,
        product_type,
        f"{instruction} {description}",
    )

    status = _normalize_string(step.get("status")) or "pending"
    if status not in VALID_STATUSES:
        status = "pending"

    result_summary = step.get("result_summary") if isinstance(step.get("result_summary"), str) else None

    normalized: dict[str, Any] = {
        "capability": capability,
        "mode": mode,
        "instruction": instruction,
        "title": title,
        "description": description,
        "inputs": _normalize_str_list(step.get("inputs")),
        "outputs": _normalize_str_list(step.get("outputs")),
        "preconditions": _normalize_str_list(step.get("preconditions")),
        "validation": _normalize_str_list(step.get("validation")),
        "success_criteria": _normalize_str_list(step.get("success_criteria")),
        "fallback": _normalize_str_list(step.get("fallback")),
        "depends_on": _normalize_depends_on(step.get("depends_on")),
        "status": status,
        "result_summary": result_summary,
    }

    if not normalized["success_criteria"] and normalized["validation"]:
        normalized["success_criteria"] = list(normalized["validation"])
    if not normalized["validation"] and normalized["success_criteria"]:
        normalized["validation"] = list(normalized["success_criteria"])

    target_scope = step.get("target_scope")
    if isinstance(target_scope, dict):
        normalized["target_scope"] = dict(target_scope)

    design_direction = _normalize_string(step.get("design_direction"))
    if design_direction:
        normalized["design_direction"] = design_direction

    step_id = step.get("id")
    if isinstance(step_id, int):
        normalized["id"] = step_id

    # Optional compatibility field consumed by retry/fallback logic.
    origin_step_id = step.get("origin_step_id")
    if isinstance(origin_step_id, int):
        normalized["origin_step_id"] = origin_step_id

    return normalized


def normalize_plan_v2(plan: list[dict[str, Any]], *, product_type: str | None) -> list[dict[str, Any]]:
    return [
        normalize_step_v2(
            step,
            product_type=product_type,
            fallback_capability="writer",
            fallback_instruction="タスクを実行する",
            fallback_title="タスク",
        )
        for step in plan
        if isinstance(step, dict)
    ]


def plan_steps_for_ui(plan: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return UI-safe shallow copies of canonical steps."""
    ui_steps: list[dict[str, Any]] = []
    for step in plan:
        if not isinstance(step, dict):
            continue
        ui_steps.append(dict(step))
    return ui_steps
