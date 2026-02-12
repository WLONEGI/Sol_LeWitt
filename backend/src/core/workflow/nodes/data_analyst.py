import logging
import json
import os
import re
import uuid
import asyncio
import mimetypes
import tempfile
from pathlib import Path
from urllib.parse import urlparse
from typing import Any, Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command

from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import DataAnalystOutput
from src.core.workflow.state import State
from src.infrastructure.storage.gcs import download_blob_as_bytes, upload_to_gcs
from .common import (
    create_worker_response,
    extract_first_json,
    resolve_selected_assets_for_step,
    split_content_parts,
)
from langchain_core.runnables import RunnableConfig
from src.core.tools import (
    bash_tool,
    package_visual_assets_tool,
    python_repl_tool,
    render_pptx_master_images_tool,
)

logger = logging.getLogger(__name__)
MAX_DATA_ANALYST_ROUNDS = 3
VALID_DATA_ANALYST_MODES = {"python_pipeline"}
STANDARD_FAILED_CHECKS = {
    "worker_execution",
    "tool_execution",
    "schema_validation",
    "missing_dependency",
    "missing_research",
    "mode_violation",
}


def _resolve_data_analyst_mode(step: dict) -> str:
    mode = str(step.get("mode") or "").strip()
    if mode in VALID_DATA_ANALYST_MODES:
        return mode
    return "python_pipeline"


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
        if _is_image_output(item.url, item.mime_type):
            urls.append(item.url)
    return urls

def _extract_python_code(tool_args: object) -> str:
    if isinstance(tool_args, dict):
        for key in ("query", "code", "input"):
            value = tool_args.get(key)
            if isinstance(value, str):
                return value
        try:
            return json.dumps(tool_args, ensure_ascii=False)
        except Exception:
            return str(tool_args)
    if isinstance(tool_args, str):
        return tool_args
    return str(tool_args)

async def _dispatch_text_delta(
    event_name: str,
    artifact_id: str,
    text: str,
    config: RunnableConfig,
    chunk_size: int = 200
) -> None:
    if not text:
        return
    for idx in range(0, len(text), chunk_size):
        chunk = text[idx:idx + chunk_size]
        await adispatch_custom_event(
            event_name,
            {"artifact_id": artifact_id, "delta": chunk},
            config=config
        )


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


def _replace_urls_with_local_paths(value: object, url_to_local: dict[str, str]) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return url_to_local.get(stripped, value)
    if isinstance(value, list):
        return [_replace_urls_with_local_paths(item, url_to_local) for item in value]
    if isinstance(value, dict):
        return {k: _replace_urls_with_local_paths(v, url_to_local) for k, v in value.items()}
    return value


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
        original_url = item.url
        local_path = _resolve_local_file_path(original_url, workspace_dir)
        if not local_path:
            continue

        file_name = os.path.basename(local_path)
        object_name = f"{output_prefix}/data_analyst/{file_name}"
        guessed_type = item.mime_type or mimetypes.guess_type(local_path)[0] or "application/octet-stream"

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
        item.url = uploaded_url
        if not item.mime_type:
            item.mime_type = guessed_type
        upload_trace.append(f"uploaded {original_url} -> {uploaded_url}")

    return upload_trace

async def data_analyst_node(state: dict, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """
    Node for the Data Analyst agent.
    
    Uses Code Execution for calculations and proceeds to Supervisor.
    """
    logger.info("Data Analyst starting task")

    result: DataAnalystOutput | None = None
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
    pptx_context = state.get("pptx_context")
    instruction = current_step.get("instruction", "")
    execution_mode = _resolve_data_analyst_mode(current_step)
    context = (
        f"Execution Mode: {execution_mode}\n\n"
        f"Instruction: {instruction}\n\n"
        f"Available Artifacts: {json.dumps(artifacts, default=str)}\n\n"
        f"Selected Step Assets: {json.dumps(selected_step_assets, ensure_ascii=False, default=str)}\n\n"
        f"Selected Image Inputs: {json.dumps(selected_image_inputs, ensure_ascii=False, default=str)}\n\n"
        f"Attachments: {json.dumps(attachments, ensure_ascii=False, default=str)}\n\n"
        f"PPTX Context: {json.dumps(pptx_context, ensure_ascii=False, default=str)}"
    )

    thread_id = config.get("configurable", {}).get("thread_id")
    user_uid = config.get("configurable", {}).get("user_uid")
    deck_title = await _get_thread_title(thread_id, user_uid) or current_step.get("title") or "Untitled"
    session_id = thread_id or str(uuid.uuid4())
    safe_title = _sanitize_filename(str(deck_title))
    output_prefix = f"generated_assets/{session_id}/{safe_title}"

    source_urls: set[str] = set()
    _collect_file_urls(selected_step_assets, source_urls)
    if not source_urls:
        _collect_file_urls(artifacts, source_urls)
        _collect_file_urls(selected_image_inputs, source_urls)
        _collect_file_urls(attachments, source_urls)
        _collect_file_urls(pptx_context, source_urls)

    artifact_id = f"step_{current_step['id']}_data"
    workspace_dir_obj = tempfile.TemporaryDirectory(prefix=f"data_analyst_{session_id}_")
    workspace_dir = workspace_dir_obj.name
    try:
        url_to_local_path, local_file_manifest = await _download_input_files(
            workspace_dir=workspace_dir,
            urls=sorted(source_urls),
        )
    except Exception as file_err:
        logger.warning("Data Analyst input file prefetch failed: %s", file_err)
        url_to_local_path = {}
        local_file_manifest = []

    context += (
        "\n\nMode Policy:\n"
        "- python_pipeline: execute general python processing only.\n"
        "\n\nFile I/O Policy:\n"
        "- All remote files are already downloaded into local workspace.\n"
        "- Use local paths only when calling tools.\n"
        "- Runtime discovers generated local files and uploads them to GCS automatically.\n"
        f"\nWorkspace Directory: {workspace_dir}\n"
        f"Local File Manifest: {json.dumps(local_file_manifest, ensure_ascii=False)}\n"
    )

    input_summary = {
        "mode": execution_mode,
        "instruction": instruction,
        "artifact_keys": list(artifacts.keys()),
        "selected_step_assets": selected_step_assets,
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
                "status": "streaming"
            },
            config=config
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch data-analyst-start: {e}")

    messages = apply_prompt_template("data_analyst", state)
    messages.append(HumanMessage(content=context, name="supervisor"))

    llm = get_llm_by_type(AGENT_LLM_MAP["data_analyst"])
    
    # Use restricted local-processing tools. GCS I/O is managed by this node.
    tools = [
        python_repl_tool,
        bash_tool,
        render_pptx_master_images_tool,
        package_visual_assets_tool,
    ]
    
    # Bind tools to LLM
    llm_with_tools = llm.bind_tools(tools)

    try:
        messages[-1].content += (
            "\n\nIMPORTANT: Only output the final result as valid JSON matching DataAnalystOutput "
            "when the Planner instruction is fully completed. If more processing is needed, "
            "call an appropriate tool (python_repl_tool, render_pptx_master_images_tool, package_visual_assets_tool, bash_tool).\n"
            "Do not include markdown wrappers.\n"
            f"Current mode is `{execution_mode}` and must be respected strictly."
        )

        # Add run_name for better visibility in events
        stream_config = config.copy()
        stream_config["run_name"] = "data_analyst"

        content_json = ""
        result_summary = ""
        is_error = False
        error_summary = ""
        tool_trace: list[str] = []
        code_trace_blocks: list[str] = []
        log_trace_blocks: list[str] = []
        detected_output_paths: set[str] = set()
        tool_error_occurred = False

        for round_index in range(MAX_DATA_ANALYST_ROUNDS):
            response = await llm_with_tools.ainvoke(messages, config=stream_config)

            tool_calls = getattr(response, "tool_calls", None) or []
            if tool_calls:
                messages.append(response)
                logger.info(f"Data Analyst triggered tool calls: {len(tool_calls)}")

                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args")
                    output = ""
                    tool_key = (tool_name or "").lower()

                    if isinstance(tool_args, dict):
                        normalized_args = dict(tool_args)
                    elif isinstance(tool_args, str):
                        normalized_args = {"input": tool_args}
                    else:
                        normalized_args = {}
                    normalized_args = _replace_urls_with_local_paths(normalized_args, url_to_local_path)

                    if "python_repl" in tool_key:
                        code_text = _extract_python_code(normalized_args)
                        if code_text:
                            code_block = f"\n# Python Run {round_index + 1}\n{code_text}\n"
                            code_trace_blocks.append(code_block)
                            try:
                                await _dispatch_text_delta("data-analyst-code-delta", artifact_id, code_block, config)
                            except Exception as e:
                                logger.warning(f"Failed to dispatch code delta: {e}")
                        try:
                            expected_files = current_step.get("outputs", [])
                            if "query" in normalized_args and "code" not in normalized_args:
                                normalized_args = {
                                    "code": normalized_args["query"],
                                    **{k: v for k, v in normalized_args.items() if k != "query"},
                                }
                            if "code" not in normalized_args and "input" in normalized_args:
                                normalized_args["code"] = normalized_args["input"]
                            normalized_args["work_dir"] = workspace_dir
                            normalized_args["expected_files"] = expected_files if isinstance(expected_files, list) else None

                            output = await python_repl_tool.ainvoke(normalized_args, config=config)
                        except Exception as e:
                            logger.error(f"Python execution failed: {e}")
                            output = f"Error executing python_repl: {e}"
                            tool_error_occurred = True
                    elif "bash" in tool_key:
                        cmd_text = normalized_args.get("cmd") or normalized_args.get("command") or str(normalized_args)
                        if cmd_text:
                            cmd_block = f"\n# Bash Run {round_index + 1}\n{cmd_text}\n"
                            code_trace_blocks.append(cmd_block)
                            try:
                                await _dispatch_text_delta("data-analyst-code-delta", artifact_id, cmd_block, config)
                            except Exception as e:
                                logger.warning(f"Failed to dispatch bash delta: {e}")
                        try:
                            if "command" in normalized_args and "cmd" not in normalized_args:
                                normalized_args = {
                                    "cmd": normalized_args["command"],
                                    **{k: v for k, v in normalized_args.items() if k != "command"},
                                }
                            normalized_args.setdefault("work_dir", workspace_dir)
                            output = await bash_tool.ainvoke(normalized_args, config=config)
                        except Exception as e:
                            logger.error(f"Bash execution failed: {e}")
                            output = f"Error executing bash: {e}"
                            tool_error_occurred = True
                    elif "render_pptx_master_images" in tool_key:
                        try:
                            normalized_args.setdefault("work_dir", workspace_dir)
                            normalized_args.setdefault("output_dir", "outputs/master_images")
                            output = await render_pptx_master_images_tool.ainvoke(normalized_args, config=config)
                        except Exception as e:
                            logger.error(f"PPTX render tool failed: {e}")
                            output = f"Error executing render_pptx_master_images_tool: {e}"
                            tool_error_occurred = True
                    elif "package_visual_assets" in tool_key:
                        try:
                            normalized_args.setdefault("work_dir", workspace_dir)
                            normalized_args.setdefault("output_dir", "outputs/packaged_assets")
                            normalized_args.setdefault("deck_title", str(deck_title))
                            output = await package_visual_assets_tool.ainvoke(normalized_args, config=config)
                        except Exception as e:
                            logger.error(f"Asset packaging tool failed: {e}")
                            output = f"Error executing package_visual_assets_tool: {e}"
                            tool_error_occurred = True
                    else:
                        output = f"Unsupported tool: {tool_name}"

                    tool_trace.append(f"{tool_name} -> {output}")
                    tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id") or tool_name or "tool"
                    messages.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))

                    if output:
                        log_block = f"\n# Output {round_index + 1}\n{output}\n"
                        log_trace_blocks.append(log_block)
                        for local_path in _extract_output_paths_from_tool_output(str(output), workspace_dir):
                            detected_output_paths.add(local_path)
                        try:
                            await _dispatch_text_delta("data-analyst-log-delta", artifact_id, log_block, config)
                        except Exception as e:
                            logger.warning(f"Failed to dispatch log delta: {e}")

                continue

            content = response.content if hasattr(response, "content") else ""
            _, text_content = split_content_parts(content)
            raw_text = text_content or (content if isinstance(content, str) else str(content))
            json_text = extract_first_json(raw_text)

            if json_text:
                try:
                    result = DataAnalystOutput.model_validate_json(json_text)
                    logger.info("✅ Data Analyst produced valid DataAnalystOutput JSON")
                    break
                except Exception as e:
                    logger.warning(f"Parsed JSON failed validation: {e}")
                    error_summary = f"Parsed JSON failed validation: {e}"
            else:
                error_summary = "No JSON found in Data Analyst output."

            if round_index < MAX_DATA_ANALYST_ROUNDS - 1:
                messages.append(
                    HumanMessage(
                        content=(
                            "Return ONLY valid JSON for DataAnalystOutput. "
                            "Do not include any extra text."
                        ),
                        name="supervisor",
                    )
                )

        if result:
            failed_checks = _normalize_failed_checks(result.failed_checks)
            if tool_error_occurred and "tool_execution" not in failed_checks:
                failed_checks = _normalize_failed_checks(failed_checks + ["tool_execution"])

            workspace_detected_files = _discover_workspace_output_files(workspace_dir)
            detected_output_paths.update(workspace_detected_files)
            _merge_detected_output_files(
                result=result,
                workspace_dir=workspace_dir,
                detected_local_paths=sorted(detected_output_paths),
            )

            implementation_code = "\n".join(block.strip() for block in code_trace_blocks if block.strip()).strip()
            execution_log = "\n".join(block.strip() for block in log_trace_blocks if block.strip()).strip()
            if implementation_code:
                result.implementation_code = implementation_code
            else:
                result.implementation_code = _normalize_text(result.implementation_code)
            if execution_log:
                result.execution_log = execution_log
            else:
                result.execution_log = _normalize_text(result.execution_log)

            summary_is_error = _looks_like_error_text(result.execution_log)
            is_error = summary_is_error or bool(failed_checks)

            if is_error and not failed_checks:
                failed_checks = _data_analyst_failed_checks(kind="worker")
            result.failed_checks = failed_checks

            if is_error:
                # Policy: partial success is treated as failure.
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
                        tool_trace.extend(upload_trace)
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
            content_json = result.model_dump_json()
            try:
                await adispatch_custom_event(
                    "data-analyst-output",
                    {
                        "artifact_id": artifact_id,
                        "output": result.model_dump(),
                        "status": "completed" if not is_error else "failed"
                    },
                    config=config
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch data-analyst-output: {e}")
        else:
            logger.warning(f"Data Analyst failed to return valid JSON: {error_summary}")
            checks = _data_analyst_failed_checks(
                kind="tool_execution" if tool_error_occurred else "schema_validation"
            )
            fallback = DataAnalystOutput(
                implementation_code="\n".join(block.strip() for block in code_trace_blocks if block.strip()).strip(),
                execution_log="\n".join(block.strip() for block in log_trace_blocks if block.strip()).strip()
                or (error_summary or "No execution log."),
                output_value=None,
                failed_checks=checks,
                output_files=[],
            )
            content_json = fallback.model_dump_json()
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
                        "output": fallback.model_dump(),
                        "status": "failed"
                    },
                    config=config
                )
            except Exception as e:
                logger.warning(f"Failed to dispatch data-analyst-output (fallback): {e}")
                 
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
        content_json = fallback.model_dump_json()
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
                    "output": fallback.model_dump(),
                    "status": "failed"
                },
                config=config
            )
        except Exception as dispatch_error:
            logger.warning(f"Failed to dispatch data-analyst-output (error): {dispatch_error}")

    try:
        await adispatch_custom_event(
            "data-analyst-complete",
            {
                "artifact_id": artifact_id,
                "status": "failed" if is_error else "completed"
            },
            config=config
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
        current_step_id=current_step['id'],
        state=state,
        artifact_key_suffix="data",
        artifact_title="Data Analysis Result",
        artifact_icon="BarChart",
        artifact_preview_urls=artifact_preview_urls,
        is_error=is_error
    )
