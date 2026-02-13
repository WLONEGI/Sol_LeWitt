import json
import re
import hashlib
import mimetypes
from typing import Any, TypeVar
from urllib.parse import urlparse
from pydantic import BaseModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.types import Command
from src.shared.config.settings import settings
from src.core.workflow.state import State
from src.infrastructure.llm.llm import ainvoke_with_retry, is_rate_limited_error

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
REMOTE_FILE_EXTS = (
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
    ".pdf", ".pptx", ".zip", ".csv", ".json", ".txt", ".md",
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


def _looks_like_remote_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme == "gs":
        return bool(parsed.netloc and parsed.path)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _looks_like_remote_file_url(value: str) -> bool:
    if not _looks_like_remote_url(value):
        return False
    lowered = value.lower()
    if lowered.endswith(REMOTE_FILE_EXTS):
        return True
    parsed = urlparse(value)
    host = (parsed.netloc or "").lower()
    return (
        parsed.scheme == "gs"
        or "storage.googleapis.com" in host
        or "googleusercontent.com" in host
    )


def _extract_urls_from_text(value: str) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    urls = re.findall(r"https?://[^\s\]\)<>\"']+", value)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in urls:
        url = raw.rstrip(".,);")
        if not url or url in seen:
            continue
        seen.add(url)
        cleaned.append(url)
    return cleaned


def _infer_mime_type_from_url(uri: str, fallback: str | None = None) -> str | None:
    if isinstance(fallback, str) and "/" in fallback:
        return fallback
    guessed, _ = mimetypes.guess_type(uri)
    if isinstance(guessed, str):
        return guessed
    lowered = uri.lower()
    if lowered.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lowered.endswith(".png"):
        return "image/png"
    if lowered.endswith(".webp"):
        return "image/webp"
    if lowered.endswith(".gif"):
        return "image/gif"
    if lowered.endswith(".pdf"):
        return "application/pdf"
    return None


def _is_image_mime(mime_type: str | None, uri: str | None = None) -> bool:
    if isinstance(mime_type, str) and mime_type.lower().startswith("image/"):
        return True
    if isinstance(uri, str):
        lowered = uri.lower()
        return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"))
    return False


def _asset_id_for(source_type: str, uri: str, artifact_id: str | None = None, producer_step_id: int | None = None) -> str:
    raw = f"{source_type}|{producer_step_id or 0}|{artifact_id or ''}|{uri}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"asset:{digest}"


def _infer_asset_role_hints(
    *,
    source_type: str,
    uri: str,
    mime_type: str | None,
    label: str | None,
    title: str | None,
    producer_mode: str | None,
) -> list[str]:
    hints: set[str] = set()
    lowered_source = str(source_type or "").lower()
    lowered_uri = str(uri or "").lower()
    lowered_mime = str(mime_type or "").lower()
    lowered_label = str(label or "").lower()
    lowered_title = str(title or "").lower()
    lowered_mode = str(producer_mode or "").lower()
    lowered_blob = " ".join([lowered_label, lowered_title, lowered_mode, lowered_uri])

    if _is_image_mime(mime_type, uri):
        hints.update({"image", "reference_image", "style_reference"})
    if "pdf" in lowered_mime or lowered_uri.endswith(".pdf"):
        hints.add("reference_document")
    if "pptx" in lowered_mime or lowered_uri.endswith(".pptx"):
        hints.update({"template_source", "layout_reference"})
    if any(token in lowered_blob for token in ("template", "layout", "master")):
        hints.update({"template_source", "layout_reference"})
    if any(token in lowered_blob for token in ("mask", "inpaint-mask", "alpha_mask")):
        hints.add("mask_image")
    if any(token in lowered_blob for token in ("base_image", "source_image", "original")):
        hints.add("base_image")
    if any(token in lowered_blob for token in ("data", "table", "dataset", "csv", "json")):
        hints.add("data_source")
    if lowered_source in {"user_upload", "selected_image_input"}:
        hints.add("user_context")
    if lowered_source == "dependency_artifact":
        hints.add("dependency_context")
    return sorted(hints)


def _append_asset(
    pool: dict[str, dict[str, Any]],
    *,
    source_type: str,
    uri: str,
    mime_type: str | None = None,
    artifact_id: str | None = None,
    producer_step_id: int | None = None,
    producer_capability: str | None = None,
    producer_mode: str | None = None,
    label: str | None = None,
    title: str | None = None,
    role_hints: list[str] | None = None,
) -> None:
    normalized_uri = str(uri or "").strip()
    if not normalized_uri:
        return
    if not _looks_like_remote_url(normalized_uri):
        return
    inferred_mime = _infer_mime_type_from_url(normalized_uri, fallback=mime_type)
    asset_id = _asset_id_for(
        source_type=source_type,
        uri=normalized_uri,
        artifact_id=artifact_id,
        producer_step_id=producer_step_id,
    )
    pool[asset_id] = {
        "asset_id": asset_id,
        "uri": normalized_uri,
        "mime_type": inferred_mime,
        "is_image": _is_image_mime(inferred_mime, normalized_uri),
        "source_type": source_type,
        "artifact_id": artifact_id,
        "producer_step_id": producer_step_id,
        "producer_capability": producer_capability,
        "producer_mode": producer_mode,
        "label": label or "",
        "title": title or "",
        "role_hints": role_hints
        if isinstance(role_hints, list) and role_hints
        else _infer_asset_role_hints(
            source_type=source_type,
            uri=normalized_uri,
            mime_type=inferred_mime,
            label=label,
            title=title,
            producer_mode=producer_mode,
        ),
    }


def _collect_assets_from_payload(
    payload: Any,
    pool: dict[str, dict[str, Any]],
    *,
    source_type: str,
    artifact_id: str | None = None,
    producer_step_id: int | None = None,
    producer_capability: str | None = None,
    producer_mode: str | None = None,
    parent_key: str | None = None,
) -> None:
    if isinstance(payload, str):
        if _looks_like_remote_file_url(payload):
            _append_asset(
                pool,
                source_type=source_type,
                uri=payload,
                artifact_id=artifact_id,
                producer_step_id=producer_step_id,
                producer_capability=producer_capability,
                producer_mode=producer_mode,
                label=parent_key,
            )
            return
        for url in _extract_urls_from_text(payload):
            if _looks_like_remote_file_url(url):
                _append_asset(
                    pool,
                    source_type=source_type,
                    uri=url,
                    artifact_id=artifact_id,
                    producer_step_id=producer_step_id,
                    producer_capability=producer_capability,
                    producer_mode=producer_mode,
                    label=parent_key or "text_url",
                )
        return

    if isinstance(payload, list):
        for item in payload:
            _collect_assets_from_payload(
                item,
                pool,
                source_type=source_type,
                artifact_id=artifact_id,
                producer_step_id=producer_step_id,
                producer_capability=producer_capability,
                producer_mode=producer_mode,
                parent_key=parent_key,
            )
        return

    if isinstance(payload, dict):
        key_to_uri_candidates = (
            "url",
            "uri",
            "image_url",
            "gcs_url",
            "source_url",
            "pdf_url",
            "file_url",
        )
        mime_hint = payload.get("mime_type") or payload.get("content_type")
        label = (
            payload.get("title")
            or payload.get("filename")
            or payload.get("caption")
            or payload.get("name")
        )
        for key in key_to_uri_candidates:
            maybe_uri = payload.get(key)
            if isinstance(maybe_uri, str) and _looks_like_remote_file_url(maybe_uri):
                _append_asset(
                    pool,
                    source_type=source_type,
                    uri=maybe_uri,
                    mime_type=mime_hint if isinstance(mime_hint, str) else None,
                    artifact_id=artifact_id,
                    producer_step_id=producer_step_id,
                    producer_capability=producer_capability,
                    producer_mode=producer_mode,
                    label=parent_key or key,
                    title=str(label) if isinstance(label, str) else None,
                )
        for key, value in payload.items():
            _collect_assets_from_payload(
                value,
                pool,
                source_type=source_type,
                artifact_id=artifact_id,
                producer_step_id=producer_step_id,
                producer_capability=producer_capability,
                producer_mode=producer_mode,
                parent_key=str(key),
            )


def build_step_asset_pool(
    state: State,
    current_step: dict[str, Any] | None = None,
    dependency_context: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    # Single-turn safety: rebuild candidate pool per-step, do not inherit prior step/turn pool.
    pool: dict[str, dict[str, Any]] = {}

    attachments = state.get("attachments") or []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        uri = item.get("url")
        if not isinstance(uri, str):
            continue
        _append_asset(
            pool,
            source_type="user_upload",
            uri=uri,
            mime_type=item.get("mime_type") if isinstance(item.get("mime_type"), str) else None,
            label=item.get("kind") if isinstance(item.get("kind"), str) else "attachment",
            title=item.get("filename") if isinstance(item.get("filename"), str) else None,
        )

    selected_image_inputs = state.get("selected_image_inputs") or []
    for item in selected_image_inputs:
        if not isinstance(item, dict):
            continue
        uri = None
        for key in ("gcs_url", "image_url", "url", "source_url"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                uri = value.strip()
                break
        if not uri:
            continue
        _append_asset(
            pool,
            source_type="selected_image_input",
            uri=uri,
            mime_type=item.get("mime_type") if isinstance(item.get("mime_type"), str) else None,
            label=item.get("provider") if isinstance(item.get("provider"), str) else "selected_image",
            title=item.get("caption") if isinstance(item.get("caption"), str) else None,
        )

    if current_step is not None and dependency_context is None:
        dependency_context = resolve_step_dependency_context(state, current_step)

    for item in (dependency_context or {}).get("resolved_dependency_artifacts", []):
        if not isinstance(item, dict):
            continue
        _collect_assets_from_payload(
            item.get("content"),
            pool,
            source_type="dependency_artifact",
            artifact_id=item.get("artifact_id") if isinstance(item.get("artifact_id"), str) else None,
            producer_step_id=item.get("producer_step_id") if isinstance(item.get("producer_step_id"), int) else None,
            producer_capability=item.get("producer_capability") if isinstance(item.get("producer_capability"), str) else None,
            producer_mode=item.get("producer_mode") if isinstance(item.get("producer_mode"), str) else None,
            parent_key="content",
        )

    return pool


def resolve_selected_assets_for_step(
    state: State,
    step_id: int | str | None,
    *,
    image_only: bool = False,
) -> list[dict[str, Any]]:
    if step_id is None:
        return []
    key = str(step_id)
    selected_map = state.get("selected_assets_by_step") or {}
    selected_ids = selected_map.get(key) if isinstance(selected_map, dict) else None
    if not isinstance(selected_ids, list):
        return []

    catalog = state.get("asset_catalog")
    if not isinstance(catalog, dict):
        catalog = {}

    resolved: list[dict[str, Any]] = []
    for asset_id in selected_ids:
        if not isinstance(asset_id, str):
            continue
        item = catalog.get(asset_id)
        if not isinstance(item, dict):
            continue
        if image_only and not bool(item.get("is_image")):
            continue
        resolved.append(item)
    return resolved


def resolve_asset_bindings_for_step(
    state: State,
    step_id: int | str | None,
) -> list[dict[str, Any]]:
    if step_id is None:
        return []
    key = str(step_id)
    bindings_map = state.get("asset_bindings_by_step") or {}
    raw_bindings = bindings_map.get(key) if isinstance(bindings_map, dict) else None
    if not isinstance(raw_bindings, list):
        return []

    catalog = state.get("asset_catalog")
    if not isinstance(catalog, dict):
        catalog = {}

    resolved: list[dict[str, Any]] = []
    for row in raw_bindings:
        if not isinstance(row, dict):
            continue
        role = row.get("role")
        if not isinstance(role, str) or not role.strip():
            continue
        asset_ids = row.get("asset_ids")
        if not isinstance(asset_ids, list):
            asset_ids = []
        assets: list[dict[str, Any]] = []
        valid_ids: list[str] = []
        for asset_id in asset_ids:
            if not isinstance(asset_id, str):
                continue
            item = catalog.get(asset_id)
            if not isinstance(item, dict):
                continue
            valid_ids.append(asset_id)
            assets.append(item)
        resolved.append(
            {
                "role": role,
                "reason": row.get("reason") if isinstance(row.get("reason"), str) else None,
                "asset_ids": valid_ids,
                "assets": assets,
            }
        )
    return resolved


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
            return await ainvoke_with_retry(
                lambda: structured_llm.ainvoke(current_messages, config=config),
                operation_name=f"structured_output.{schema.__name__}",
            )
        except Exception as e:
            if is_rate_limited_error(e):
                raise
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
    
    # 1. Main Response (compact context only; full payload lives in artifacts)
    worker_capability = _normalize_worker_capability(capability or role)
    message_name = emitter_name or role
    status_label = "completed" if not is_error else "error"
    artifact_id = f"step_{current_step_id}_{artifact_key_suffix}"
    compact_payload = {
        "artifact_id": artifact_id,
        "status": status_label,
        "result_summary": result_summary,
    }
    response_format = settings.RESPONSE_FORMAT or "Role: {role}\nContent: {content}"
    response_content = response_format.format(
        role=worker_capability,
        content=json.dumps(compact_payload, ensure_ascii=False),
    )

    main_message = AIMessage(
        content=response_content, 
        name=message_name
    )

    # 2. Worker Result UI Message
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
