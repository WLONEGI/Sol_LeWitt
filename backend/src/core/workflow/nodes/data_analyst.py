import logging
import json
import os
import re
import uuid
import asyncio
import mimetypes
import tempfile
import inspect
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Literal

from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command

from src.shared.schemas import DataAnalystOutput
from src.core.workflow.state import State
from src.infrastructure.storage.gcs import download_blob_as_bytes, upload_to_gcs
from .common import (
    create_worker_response,
    resolve_asset_bindings_for_step,
    resolve_step_dependency_context,
    resolve_selected_assets_for_step,
)
from langchain_core.runnables import RunnableConfig
from src.core.tools import (
    package_visual_assets_tool,
    render_pptx_master_images_tool,
)

logger = logging.getLogger(__name__)
VALID_DATA_ANALYST_MODES = {
    "pptx_master_to_images",
    "pptx_slides_to_images",
    "images_to_package",
    "template_manifest_extract",
}
STANDARD_FAILED_CHECKS = {
    "worker_execution",
    "tool_execution",
    "schema_validation",
    "missing_dependency",
    "missing_research",
    "mode_violation",
}


def _resolve_data_analyst_mode(step: dict) -> str:
    mode = str(step.get("mode") or "").strip().lower()
    if mode in VALID_DATA_ANALYST_MODES:
        return mode

    # Legacy compatibility: infer deterministic mode from instruction text.
    instruction = str(step.get("instruction") or "").lower()
    if any(token in instruction for token in ("zip", "pdf", "pptx化", "パッケージ", "書き出し")):
        return "images_to_package"
    if "マスター" in instruction or "master" in instruction:
        return "pptx_master_to_images"
    if "スライド" in instruction or "content" in instruction:
        return "pptx_slides_to_images"
    return "template_manifest_extract"


def _collect_assets_from_bindings_by_roles(
    bindings: list[dict[str, Any]],
    roles: set[str],
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            continue
        role = binding.get("role")
        if not isinstance(role, str) or role not in roles:
            continue
        assets = binding.get("assets")
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            asset_id = asset.get("asset_id")
            if isinstance(asset_id, str) and asset_id in seen_ids:
                continue
            if isinstance(asset_id, str):
                seen_ids.add(asset_id)
            collected.append(asset)
    return collected


def _data_analyst_failed_checks(
    *,
    kind: str,
    extras: list[str] | None = None,
) -> list[str]:
    mapping = {
        "worker": ["worker_execution"],
        "schema_validation": ["worker_execution", "schema_validation"],
        "tool_execution": ["worker_execution", "tool_execution"],
        "missing_dependency": ["worker_execution", "missing_dependency"],
        "mode_violation": ["worker_execution", "mode_violation"],
    }
    checks = list(mapping.get(kind, ["worker_execution"]))
    if extras:
        checks.extend(str(item) for item in extras if isinstance(item, str))
    return _normalize_failed_checks(checks)


def _normalize_failed_checks(checks: object) -> list[str]:
    if not isinstance(checks, list):
        return []
    normalized: list[str] = []
    has_unknown = False
    for item in checks:
        if not isinstance(item, str):
            continue
        code = item.strip()
        if not code:
            continue
        if code not in STANDARD_FAILED_CHECKS:
            has_unknown = True
            continue
        if code not in normalized:
            normalized.append(code)

    if has_unknown:
        for code in ("worker_execution", "schema_validation"):
            if code not in normalized:
                normalized.append(code)

    return normalized


def _looks_like_error_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return "error" in lowered or "失敗" in text or "エラー" in text or "failed" in lowered


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _discover_local_paths_from_value(
    value: Any,
    workspace_dir: str,
    output: set[str],
) -> None:
    if isinstance(value, str):
        local_path = _resolve_local_file_path(value, workspace_dir)
        if local_path:
            output.add(local_path)
        return
    if isinstance(value, list):
        for item in value:
            _discover_local_paths_from_value(item, workspace_dir, output)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _discover_local_paths_from_value(nested, workspace_dir, output)


def _extract_created_files_from_python_output(output_text: str, workspace_dir: str) -> list[str]:
    if not isinstance(output_text, str) or "Created files:" not in output_text:
        return []
    section = output_text.split("Created files:", 1)[1]
    lines: list[str] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not line:
            if lines:
                break
            continue
        if line.lower().startswith("missing expected files"):
            break
        lines.append(line)

    resolved: list[str] = []
    for candidate in lines:
        local_path = _resolve_local_file_path(candidate, workspace_dir)
        if local_path and local_path not in resolved:
            resolved.append(local_path)
    return resolved


def _extract_output_paths_from_tool_output(tool_output: str, workspace_dir: str) -> list[str]:
    discovered: set[str] = set()
    if not isinstance(tool_output, str):
        return []

    json_candidate: Any = None
    try:
        json_candidate = json.loads(tool_output)
    except Exception:
        json_candidate = None

    if json_candidate is not None:
        _discover_local_paths_from_value(json_candidate, workspace_dir, discovered)

    for candidate in _extract_created_files_from_python_output(tool_output, workspace_dir):
        discovered.add(candidate)

    return sorted(discovered)


def _discover_workspace_output_files(workspace_dir: str) -> list[str]:
    workspace_root = Path(workspace_dir).resolve()
    preferred_roots = [workspace_root / "outputs"]
    fallback_roots = [workspace_root]

    discovered: list[str] = []

    def _walk(root: Path, allow_inputs: bool) -> None:
        if not root.exists():
            return
        for candidate in root.rglob("*"):
            if not candidate.is_file():
                continue
            if not allow_inputs and "inputs" in candidate.parts:
                continue
            resolved = str(candidate.resolve())
            if resolved not in discovered:
                discovered.append(resolved)

    for root in preferred_roots:
        _walk(root, allow_inputs=False)
    if discovered:
        return sorted(discovered)

    for root in fallback_roots:
        _walk(root, allow_inputs=False)
    return sorted(discovered)


def _merge_detected_output_files(
    *,
    result: DataAnalystOutput,
    workspace_dir: str,
    detected_local_paths: list[str],
) -> None:
    existing_items = list(result.output_files or [])
    normalized_candidates: set[str] = set()
    for item in existing_items:
        local_path = _resolve_local_file_path(item.url, workspace_dir)
        if local_path:
            normalized_candidates.add(local_path)
    for candidate in detected_local_paths:
        local_path = _resolve_local_file_path(candidate, workspace_dir)
        if local_path:
            normalized_candidates.add(local_path)

    existing_by_local: dict[str, Any] = {}
    for item in existing_items:
        local_path = _resolve_local_file_path(item.url, workspace_dir)
        if local_path:
            existing_by_local[local_path] = item

    merged: list[dict[str, Any]] = []
    workspace_root = Path(workspace_dir).resolve()
    for local_path in sorted(normalized_candidates):
        existing = existing_by_local.get(local_path)
        relative_url = os.path.relpath(local_path, workspace_root)
        if relative_url.startswith(".."):
            relative_url = local_path
        mime_type = None
        title = None
        if existing is not None:
            mime_type = existing.mime_type
            title = existing.title
        if not isinstance(mime_type, str) or not mime_type:
            mime_type = mimetypes.guess_type(local_path)[0] or "application/octet-stream"
        if not isinstance(title, str) or not title:
            title = os.path.basename(local_path)
        merged.append(
            {
                "url": relative_url.replace("\\", "/"),
                "title": title,
                "mime_type": mime_type,
            }
        )

    result.output_files = merged


def _summarize_data_analyst_result(
    *,
    is_error: bool,
    failed_checks: list[str],
    output_files: list[Any],
    output_value: Any,
) -> str:
    if is_error:
        if failed_checks:
            return f"Error: Data analyst task failed ({', '.join(failed_checks)})."
        return "Error: Data analyst task failed."
    if output_files:
        return f"Data analyst task completed ({len(output_files)} files generated)."
    if output_value is not None:
        return "Data analyst task completed (non-file output generated)."
    return "Data analyst task completed."

def _sanitize_filename(title: str) -> str:
    safe = re.sub(r"[\\\\/:*?\"<>|]", "_", title).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or "Untitled"


def _extract_tool_source_code(tool_obj: Any) -> str:
    tool_func = getattr(tool_obj, "func", None)
    if not callable(tool_func):
        return ""
    try:
        return inspect.getsource(tool_func).strip()
    except Exception:
        return ""


def _build_tool_implementation_code(tool_obj: Any, call_expression: str) -> str:
    source = _extract_tool_source_code(tool_obj)
    if not source:
        return call_expression
    return (
        "# Tool Invocation\n"
        f"{call_expression}\n\n"
        "# Tool Source\n"
        f"{source}"
    )

async def _get_thread_title(thread_id: str | None, owner_uid: str | None) -> str | None:
    if not thread_id or not owner_uid:
        return None
    try:
        from src.core.workflow.service import _manager
        if not _manager.pool:
            return None
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT title FROM threads WHERE thread_id = %s AND owner_uid = %s",
                    (thread_id, owner_uid),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return row[0]
    except Exception as e:
        logger.warning(f"Failed to fetch thread title: {e}")
    return None

def _is_image_output(url: str, mime_type: str | None) -> bool:
    if mime_type and mime_type.startswith("image/"):
        return True
    lowered = (url or "").lower()
    return lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))

def _extract_preview_urls(result: DataAnalystOutput | None) -> list[str]:
    if not result:
        return []
    urls: list[str] = []
    for item in result.output_files:
        if isinstance(item, dict):
            url = str(item.get("url") or "")
            mime_type = item.get("mime_type") if isinstance(item.get("mime_type"), str) else None
        else:
            url = str(getattr(item, "url", "") or "")
            raw_mime = getattr(item, "mime_type", None)
            mime_type = raw_mime if isinstance(raw_mime, str) else None
        if _is_image_output(url, mime_type):
            urls.append(url)
    return urls

def _is_remote_url(value: str) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value.strip())
    if parsed.scheme == "gs":
        return bool(parsed.netloc and parsed.path)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _looks_like_file_url(value: str) -> bool:
    if not _is_remote_url(value):
        return False
    lowered = value.lower()
    file_exts = (
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
        ".pdf", ".pptx", ".zip", ".csv", ".json", ".txt", ".md",
    )
    if lowered.endswith(file_exts):
        return True
    parsed = urlparse(value)
    host = (parsed.netloc or "").lower()
    return (
        parsed.scheme == "gs"
        or "storage.googleapis.com" in host
        or "googleusercontent.com" in host
    )


def _collect_file_urls(value: object, output: set[str]) -> None:
    if isinstance(value, str):
        if _looks_like_file_url(value):
            output.add(value.strip())
        return
    if isinstance(value, list):
        for item in value:
            _collect_file_urls(item, output)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_file_urls(nested, output)


def _extract_visualizer_generated_image_urls(dependency_context: dict[str, Any]) -> list[str]:
    raw_dependencies = (dependency_context or {}).get("resolved_dependency_artifacts")
    if not isinstance(raw_dependencies, list):
        return []

    ranked_urls: list[tuple[int, str]] = []
    seen: set[str] = set()

    for item in raw_dependencies:
        if not isinstance(item, dict):
            continue
        if str(item.get("producer_capability") or "") != "visualizer":
            continue

        content = item.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                continue
        if not isinstance(content, dict):
            continue

        prompts = content.get("prompts")
        if isinstance(prompts, list):
            for prompt in prompts:
                if not isinstance(prompt, dict):
                    continue
                url = prompt.get("generated_image_url")
                slide_number = prompt.get("slide_number")
                if not isinstance(url, str) or not url.strip():
                    continue
                if not _looks_like_file_url(url):
                    continue
                normalized = url.strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                rank = slide_number if isinstance(slide_number, int) and slide_number > 0 else 10**9
                ranked_urls.append((rank, normalized))

        slides = content.get("slides")
        if isinstance(slides, list):
            for slide in slides:
                if not isinstance(slide, dict):
                    continue
                url = slide.get("image_url")
                slide_number = slide.get("slide_number")
                if not isinstance(url, str) or not url.strip():
                    continue
                if not _looks_like_file_url(url):
                    continue
                normalized = url.strip()
                if normalized in seen:
                    continue
                seen.add(normalized)
                rank = slide_number if isinstance(slide_number, int) and slide_number > 0 else 10**9
                ranked_urls.append((rank, normalized))

    ranked_urls.sort(key=lambda row: (row[0], row[1]))
    return [url for _, url in ranked_urls]


def _safe_filename_from_url(url: str, index: int) -> str:
    parsed = urlparse(url)
    name = os.path.basename(parsed.path or "")
    if not name:
        name = f"file_{index:03d}.bin"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    if not safe:
        safe = f"file_{index:03d}.bin"
    return f"{index:03d}_{safe}"


async def _download_input_files(
    *,
    workspace_dir: str,
    urls: list[str],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    inputs_dir = os.path.join(workspace_dir, "inputs")
    os.makedirs(inputs_dir, exist_ok=True)

    url_to_local: dict[str, str] = {}
    manifest: list[dict[str, str]] = []

    for index, source_url in enumerate(urls, start=1):
        payload = await asyncio.to_thread(download_blob_as_bytes, source_url)
        if payload is None:
            logger.warning("Data Analyst failed to fetch input file: %s", source_url)
            continue

        filename = _safe_filename_from_url(source_url, index)
        local_path = os.path.join(inputs_dir, filename)
        with open(local_path, "wb") as fp:
            fp.write(payload)

        url_to_local[source_url] = local_path
        manifest.append(
            {
                "source_url": source_url,
                "local_path": local_path,
            }
        )

    return url_to_local, manifest


def _resolve_local_file_path(value: str, workspace_dir: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None

    source = value.strip()
    if _is_remote_url(source):
        return None

    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = Path(workspace_dir) / candidate

    resolved = str(candidate.resolve())
    workspace_root = str(Path(workspace_dir).resolve())
    if not resolved.startswith(workspace_root):
        return None
    if not os.path.isfile(resolved):
        return None
    return resolved


async def _upload_result_files_to_gcs(
    *,
    result: DataAnalystOutput,
    workspace_dir: str,
    output_prefix: str,
) -> list[str]:
    upload_trace: list[str] = []
    for item in result.output_files:
        original_url = ""
        mime_type: str | None = None
        if isinstance(item, dict):
            original_url = str(item.get("url") or "")
            mime_type = item.get("mime_type") if isinstance(item.get("mime_type"), str) else None
        else:
            original_url = str(getattr(item, "url", "") or "")
            raw_mime = getattr(item, "mime_type", None)
            mime_type = raw_mime if isinstance(raw_mime, str) else None

        local_path = _resolve_local_file_path(original_url, workspace_dir)
        if not local_path:
            continue

        file_name = os.path.basename(local_path)
        object_name = f"{output_prefix}/data_analyst/{file_name}"
        guessed_type = mime_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"

        with open(local_path, "rb") as fp:
            payload = fp.read()

        uploaded_url = await asyncio.to_thread(
            upload_to_gcs,
            payload,
            guessed_type,
            None,
            None,
            object_name,
        )
        if isinstance(item, dict):
            item["url"] = uploaded_url
            if not isinstance(item.get("mime_type"), str) or not item.get("mime_type"):
                item["mime_type"] = guessed_type
        else:
            setattr(item, "url", uploaded_url)
            if not isinstance(getattr(item, "mime_type", None), str) or not getattr(item, "mime_type", None):
                setattr(item, "mime_type", guessed_type)
        upload_trace.append(f"uploaded {original_url} -> {uploaded_url}")

    return upload_trace

def _pick_first_local_pptx(local_file_manifest: list[dict[str, str]]) -> str | None:
    for item in local_file_manifest:
        local_path = item.get("local_path")
        if not isinstance(local_path, str):
            continue
        if local_path.lower().endswith(".pptx") and os.path.isfile(local_path):
            return local_path
    return None


def _pick_local_images(
    local_file_manifest: list[dict[str, str]],
    preferred_source_urls: list[str] | None = None,
) -> list[str]:
    image_exts = (".png", ".jpg", ".jpeg", ".webp", ".gif")
    by_source_url: dict[str, str] = {}
    images: list[str] = []

    for item in local_file_manifest:
        source_url = item.get("source_url")
        local_path = item.get("local_path")
        if isinstance(source_url, str) and isinstance(local_path, str):
            by_source_url[source_url] = local_path

    if isinstance(preferred_source_urls, list) and preferred_source_urls:
        preferred_images: list[str] = []
        seen_local_paths: set[str] = set()
        for source_url in preferred_source_urls:
            local_path = by_source_url.get(source_url)
            if not isinstance(local_path, str):
                continue
            if local_path in seen_local_paths:
                continue
            if not os.path.isfile(local_path):
                continue
            if not local_path.lower().endswith(image_exts):
                continue
            seen_local_paths.add(local_path)
            preferred_images.append(local_path)
        if preferred_images:
            return preferred_images

    for item in local_file_manifest:
        local_path = item.get("local_path")
        if not isinstance(local_path, str):
            continue
        if not os.path.isfile(local_path):
            continue
        if local_path.lower().endswith(image_exts):
            images.append(local_path)
    return images


def _build_template_manifest_output(
    *,
    pptx_context: Any,
    local_file_manifest: list[dict[str, str]],
) -> dict[str, Any]:
    if isinstance(pptx_context, dict):
        templates = pptx_context.get("templates")
        if isinstance(templates, list):
            return {
                "template_count": len(templates),
                "templates": templates,
            }
        primary = pptx_context.get("primary")
        if isinstance(primary, dict):
            return {
                "template_count": int(pptx_context.get("template_count") or 1),
                "templates": [primary],
            }

    pptx_paths = [item.get("source_url") for item in local_file_manifest if str(item.get("local_path") or "").lower().endswith(".pptx")]
    return {
        "template_count": len(pptx_paths),
        "templates": [{"source_url": url} for url in pptx_paths if isinstance(url, str)],
    }


async def _run_deterministic_data_analyst_mode(
    *,
    mode: str,
    instruction: str,
    deck_title: str,
    workspace_dir: str,
    local_file_manifest: list[dict[str, str]],
    preferred_image_source_urls: list[str],
    pptx_context: Any,
    config: RunnableConfig,
) -> tuple[DataAnalystOutput, set[str]]:
    detected_output_paths: set[str] = set()

    if mode in {"pptx_master_to_images", "pptx_slides_to_images"}:
        pptx_path = _pick_first_local_pptx(local_file_manifest)
        if not pptx_path:
            return (
                DataAnalystOutput(
                    implementation_code=f"mode={mode}",
                    execution_log="Error: PPTX input not found.",
                    output_value=None,
                    failed_checks=_data_analyst_failed_checks(kind="missing_dependency"),
                    output_files=[],
                ),
                detected_output_paths,
            )

        output_dir = "outputs/master_images" if mode == "pptx_master_to_images" else "outputs/slide_images"
        tool_output = await render_pptx_master_images_tool.ainvoke(
            {
                "pptx_path": pptx_path,
                "output_dir": output_dir,
                "work_dir": workspace_dir,
            },
            config=config,
        )
        tool_output_text = str(tool_output)
        detected_output_paths.update(_extract_output_paths_from_tool_output(tool_output_text, workspace_dir))
        failed_checks = _data_analyst_failed_checks(kind="tool_execution") if tool_output_text.strip().startswith("Error:") else []
        call_expression = (
            f"render_pptx_master_images_tool("
            f"pptx_path={pptx_path!r}, output_dir={output_dir!r})"
        )
        return (
            DataAnalystOutput(
                implementation_code=_build_tool_implementation_code(
                    render_pptx_master_images_tool,
                    call_expression,
                ),
                execution_log=tool_output_text,
                output_value={
                    "mode": mode,
                    "instruction": instruction,
                    "source_pptx": pptx_path,
                },
                failed_checks=failed_checks,
                output_files=[],
            ),
            detected_output_paths,
        )

    if mode == "images_to_package":
        image_paths = _pick_local_images(
            local_file_manifest,
            preferred_source_urls=preferred_image_source_urls,
        )
        if not image_paths:
            return (
                DataAnalystOutput(
                    implementation_code="mode=images_to_package",
                    execution_log="Error: image inputs not found.",
                    output_value=None,
                    failed_checks=_data_analyst_failed_checks(kind="missing_dependency"),
                    output_files=[],
                ),
                detected_output_paths,
            )

        tool_output = await package_visual_assets_tool.ainvoke(
            {
                "image_paths": image_paths,
                "output_basename": _sanitize_filename(deck_title).replace(" ", "_"),
                "output_dir": "outputs/packaged_assets",
                "deck_title": deck_title,
                "work_dir": workspace_dir,
            },
            config=config,
        )
        tool_output_text = str(tool_output)
        detected_output_paths.update(_extract_output_paths_from_tool_output(tool_output_text, workspace_dir))
        failed_checks = _data_analyst_failed_checks(kind="tool_execution") if tool_output_text.strip().startswith("Error:") else []
        call_expression = (
            "package_visual_assets_tool("
            f"image_paths=image_paths,  # {len(image_paths)} files\n"
            f"    output_basename={_sanitize_filename(deck_title).replace(' ', '_')!r},\n"
            "    output_dir='outputs/packaged_assets',\n"
            f"    deck_title={deck_title!r}\n"
            ")"
        )
        return (
            DataAnalystOutput(
                implementation_code=_build_tool_implementation_code(
                    package_visual_assets_tool,
                    call_expression,
                ),
                execution_log=tool_output_text,
                output_value={
                    "mode": mode,
                    "instruction": instruction,
                    "input_images": len(image_paths),
                },
                failed_checks=failed_checks,
                output_files=[],
            ),
            detected_output_paths,
        )

    if mode == "template_manifest_extract":
        output_value = _build_template_manifest_output(
            pptx_context=pptx_context,
            local_file_manifest=local_file_manifest,
        )
        return (
            DataAnalystOutput(
                implementation_code="template_manifest_extract",
                execution_log="Template manifest extracted.",
                output_value=output_value,
                failed_checks=[],
                output_files=[],
            ),
            detected_output_paths,
        )

    return (
        DataAnalystOutput(
            implementation_code=f"mode={mode}",
            execution_log=f"Error: Unsupported data_analyst mode '{mode}'.",
            output_value=None,
            failed_checks=_data_analyst_failed_checks(kind="mode_violation"),
            output_files=[],
        ),
        detected_output_paths,
    )


async def data_analyst_node(state: dict, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """Data Analyst worker node (deterministic mode execution)."""
    logger.info("Data Analyst starting task")

    is_error = False
    artifact_preview_urls: list[str] = []
    workspace_dir_obj: tempfile.TemporaryDirectory[str] | None = None
    artifact_id = "step_unknown_data"

    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"])
            if step.get("status") == "in_progress"
            and step.get("capability") == "data_analyst"
        )
    except StopIteration:
        logger.error("Data Analyst called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    artifacts = state.get("artifacts", {}) or {}
    selected_image_inputs = state.get("selected_image_inputs") or []
    attachments = state.get("attachments") or []
    selected_step_assets = resolve_selected_assets_for_step(state, current_step.get("id"))
    selected_asset_bindings = resolve_asset_bindings_for_step(state, current_step.get("id"))
    dependency_context = resolve_step_dependency_context(state, current_step)
    preferred_visualizer_image_urls = _extract_visualizer_generated_image_urls(dependency_context)
    pptx_context = state.get("pptx_context")
    instruction = current_step.get("instruction", "")
    execution_mode = _resolve_data_analyst_mode(current_step)

    thread_id = config.get("configurable", {}).get("thread_id")
    user_uid = config.get("configurable", {}).get("user_uid")
    deck_title = await _get_thread_title(thread_id, user_uid) or current_step.get("title") or "Untitled"
    session_id = thread_id or str(uuid.uuid4())
    safe_title = _sanitize_filename(str(deck_title))
    output_prefix = f"generated_assets/{session_id}/{safe_title}"

    source_urls: set[str] = set()
    binding_priority_assets = _collect_assets_from_bindings_by_roles(
        selected_asset_bindings,
        roles={"template_source", "layout_reference", "data_source"},
    )
    _collect_file_urls(binding_priority_assets, source_urls)
    _collect_file_urls(selected_step_assets, source_urls)
    if execution_mode == "images_to_package":
        for url in preferred_visualizer_image_urls:
            source_urls.add(url)
        _collect_file_urls(dependency_context.get("resolved_dependency_artifacts", []), source_urls)
    elif not source_urls:
        _collect_file_urls(dependency_context.get("resolved_dependency_artifacts", []), source_urls)
    if not source_urls:
        _collect_file_urls(selected_image_inputs, source_urls)
        _collect_file_urls(attachments, source_urls)
        _collect_file_urls(pptx_context, source_urls)

    artifact_id = f"step_{current_step['id']}_data"
    workspace_dir_obj = tempfile.TemporaryDirectory(prefix=f"data_analyst_{session_id}_")
    workspace_dir = workspace_dir_obj.name
    try:
        _url_to_local_path, local_file_manifest = await _download_input_files(
            workspace_dir=workspace_dir,
            urls=sorted(source_urls),
        )
    except Exception as file_err:
        logger.warning("Data Analyst input file prefetch failed: %s", file_err)
        local_file_manifest = []

    input_summary = {
        "mode": execution_mode,
        "instruction": instruction,
        "artifact_keys": list(artifacts.keys()),
        "selected_step_assets": selected_step_assets,
        "selected_asset_bindings": selected_asset_bindings,
        "planned_inputs": dependency_context.get("planned_inputs", []),
        "depends_on_step_ids": dependency_context.get("depends_on_step_ids", []),
        "resolved_dependency_artifacts": dependency_context.get("resolved_dependency_artifacts", []),
        "selected_image_inputs": selected_image_inputs,
        "attachments": attachments,
        "pptx_context": pptx_context,
        "output_prefix": output_prefix,
        "deck_title": deck_title,
        "session_id": session_id,
        "workspace_dir": workspace_dir,
        "local_file_manifest": local_file_manifest,
    }

    try:
        await adispatch_custom_event(
            "data-analyst-start",
            {
                "artifact_id": artifact_id,
                "title": current_step.get("title") or "Data Analyst",
                "input": input_summary,
                "status": "streaming",
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch data-analyst-start: {e}")

    try:
        result, detected_output_paths = await _run_deterministic_data_analyst_mode(
            mode=execution_mode,
            instruction=str(instruction),
            deck_title=str(deck_title),
            workspace_dir=workspace_dir,
            local_file_manifest=local_file_manifest,
            preferred_image_source_urls=preferred_visualizer_image_urls,
            pptx_context=pptx_context,
            config=config,
        )

        failed_checks = _normalize_failed_checks(result.failed_checks)
        if _looks_like_error_text(result.execution_log):
            failed_checks = _normalize_failed_checks(failed_checks + _data_analyst_failed_checks(kind="tool_execution"))
        result.failed_checks = failed_checks
        is_error = bool(failed_checks)

        workspace_detected_files = _discover_workspace_output_files(workspace_dir)
        detected_output_paths.update(workspace_detected_files)
        _merge_detected_output_files(
            result=result,
            workspace_dir=workspace_dir,
            detected_local_paths=sorted(detected_output_paths),
        )

        if is_error:
            result.output_files = []
            result.output_value = None
            artifact_preview_urls = []
        else:
            try:
                upload_trace = await _upload_result_files_to_gcs(
                    result=result,
                    workspace_dir=workspace_dir,
                    output_prefix=output_prefix,
                )
                if upload_trace:
                    result.execution_log = (
                        f"{result.execution_log}\n\n# Upload Trace\n" + "\n".join(upload_trace)
                    ).strip()
            except Exception as upload_err:
                logger.error("Failed to upload output files to GCS: %s", upload_err)
                result.failed_checks = _normalize_failed_checks(result.failed_checks + ["tool_execution"])
                result.output_files = []
                result.output_value = None
                is_error = True

            artifact_preview_urls = _extract_preview_urls(result) if not is_error else []

        result_summary = _summarize_data_analyst_result(
            is_error=is_error,
            failed_checks=result.failed_checks,
            output_files=result.output_files,
            output_value=result.output_value,
        )
        result_payload = result.model_dump()
        result_payload["input"] = input_summary
        content_json = json.dumps(result_payload, ensure_ascii=False)

        try:
            await adispatch_custom_event(
                "data-analyst-output",
                {
                    "artifact_id": artifact_id,
                    "output": result_payload,
                    "status": "completed" if not is_error else "failed",
                },
                config=config,
            )
        except Exception as e:
            logger.warning(f"Failed to dispatch data-analyst-output: {e}")
    except Exception as e:
        logger.error(f"Data Analyst failed: {e}")
        checks = _data_analyst_failed_checks(kind="worker")
        fallback = DataAnalystOutput(
            implementation_code="",
            execution_log=str(e),
            output_value=None,
            failed_checks=checks,
            output_files=[],
        )
        fallback_payload = fallback.model_dump()
        fallback_payload["input"] = input_summary
        content_json = json.dumps(fallback_payload, ensure_ascii=False)
        result_summary = _summarize_data_analyst_result(
            is_error=True,
            failed_checks=checks,
            output_files=[],
            output_value=None,
        )
        is_error = True
        artifact_preview_urls = []
        try:
            await adispatch_custom_event(
                "data-analyst-output",
                {
                    "artifact_id": artifact_id,
                    "output": fallback_payload,
                    "status": "failed",
                },
                config=config,
            )
        except Exception as dispatch_error:
            logger.warning(f"Failed to dispatch data-analyst-output (error): {dispatch_error}")

    try:
        await adispatch_custom_event(
            "data-analyst-complete",
            {
                "artifact_id": artifact_id,
                "status": "failed" if is_error else "completed",
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch data-analyst-complete: {e}")

    if workspace_dir_obj is not None:
        workspace_dir_obj.cleanup()
    current_step["result_summary"] = result_summary

    return create_worker_response(
        role="data_analyst",
        content_json=content_json,
        result_summary=result_summary,
        current_step_id=current_step["id"],
        state=state,
        artifact_key_suffix="data",
        artifact_title="Data Analysis Result",
        artifact_icon="BarChart",
        artifact_preview_urls=artifact_preview_urls,
        is_error=is_error,
    )
