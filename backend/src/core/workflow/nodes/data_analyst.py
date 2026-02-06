import logging
import json
import re
import uuid
import asyncio
from typing import Literal

from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command

from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import DataAnalystOutput
from src.core.workflow.state import State
from .common import create_worker_response, extract_first_json, split_content_parts
from langchain_core.runnables import RunnableConfig

logger = logging.getLogger(__name__)
MAX_DATA_ANALYST_ROUNDS = 3

def _sanitize_filename(title: str) -> str:
    safe = re.sub(r"[\\\\/:*?\"<>|]", "_", title).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or "Untitled"

def _safe_json_loads(value: object) -> dict | None:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    if isinstance(value, dict):
        return value
    return None

def _get_latest_artifact_by_suffix(artifacts: dict, suffix: str) -> dict | None:
    candidates: list[tuple[int, str]] = []
    for key in artifacts.keys():
        if key.endswith(suffix):
            match = re.search(r"step_(\d+)_", key)
            step_id = int(match.group(1)) if match else -1
            candidates.append((step_id, key))
    if not candidates:
        return None
    _, key = sorted(candidates, key=lambda x: x[0])[-1]
    return _safe_json_loads(artifacts.get(key))

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

async def data_analyst_node(state: dict, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """
    Node for the Data Analyst agent.
    
    Uses Code Execution for calculations and proceeds to Supervisor.
    """
    logger.info("Data Analyst starting task")

    result: DataAnalystOutput | None = None
    is_error = False
    artifact_preview_urls: list[str] = []

    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "data_analyst"
        )
    except StopIteration:
        logger.error("Data Analyst called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    artifacts = state.get("artifacts", {}) or {}
    instruction = current_step.get("instruction", "")
    context = (
        f"Instruction: {instruction}\n\n"
        f"Available Artifacts: {json.dumps(artifacts, default=str)}"
    )

    thread_id = config.get("configurable", {}).get("thread_id")
    user_uid = config.get("configurable", {}).get("user_uid")
    deck_title = await _get_thread_title(thread_id, user_uid) or current_step.get("title") or "Untitled"
    session_id = thread_id or str(uuid.uuid4())
    safe_title = _sanitize_filename(str(deck_title))
    output_prefix = f"generated_assets/{session_id}/{safe_title}"

    visual_data = _get_latest_artifact_by_suffix(artifacts, "_visual") or {}
    visual_prompts = visual_data.get("prompts", []) if isinstance(visual_data, dict) else []
    visual_image_urls = [
        p.get("generated_image_url")
        for p in visual_prompts
        if isinstance(p, dict) and p.get("generated_image_url")
    ]

    if visual_image_urls:
        context += (
            "\n\nAUTO_TASK: Visualizer outputs detected. You MUST generate a PDF and a TAR "
            "from the image URLs and upload them to GCS. Use the output_prefix and deck_title "
            "for object naming.\n"
            f"- deck_title: {deck_title}\n"
            f"- session_id: {session_id}\n"
            f"- output_prefix: {output_prefix}\n"
            f"- image_urls: {json.dumps(visual_image_urls, ensure_ascii=False)}\n"
        )

    artifact_id = f"step_{current_step['id']}_data"
    input_summary = {
        "instruction": instruction,
        "artifact_keys": list(artifacts.keys()),
        "output_prefix": output_prefix,
        "deck_title": deck_title,
        "session_id": session_id,
        "auto_task": {
            "type": "visualizer_package",
            "image_urls": visual_image_urls
        } if visual_image_urls else None
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

    from langchain_experimental.tools import PythonREPLTool
    
    llm = get_llm_by_type(AGENT_LLM_MAP["data_analyst"])
    
    # Use standard PythonREPLTool
    repl_tool = PythonREPLTool()
    
    # Bind tool to LLM
    llm_with_code_exec = llm.bind_tools([repl_tool])

    try:
        messages[-1].content += (
            "\n\nIMPORTANT: Only output the final result as valid JSON matching DataAnalystOutput "
            "when the Planner instruction is fully completed. If more processing is needed, "
            "call the python_repl tool."
        )

        # Add run_name for better visibility in events
        stream_config = config.copy()
        stream_config["run_name"] = "data_analyst"

        content_json = ""
        result_summary = ""
        is_error = False
        error_summary = ""
        tool_trace: list[str] = []

        for round_index in range(MAX_DATA_ANALYST_ROUNDS):
            response = await llm_with_code_exec.ainvoke(messages, config=stream_config)

            tool_calls = getattr(response, "tool_calls", None) or []
            if tool_calls:
                messages.append(response)
                logger.info(f"Data Analyst triggered tool calls: {len(tool_calls)}")

                for tool_call in tool_calls:
                    tool_name = tool_call.get("name")
                    tool_args = tool_call.get("args")
                    output = ""
                    tool_key = (tool_name or "").lower()
                    if tool_key == "python_repl":
                        code_text = _extract_python_code(tool_args)
                        if code_text:
                            code_block = f"\n# Run {round_index + 1}\n{code_text}\n"
                            try:
                                await _dispatch_text_delta(
                                    "data-analyst-code-delta",
                                    artifact_id,
                                    code_block,
                                    config
                                )
                            except Exception as e:
                                logger.warning(f"Failed to dispatch code delta: {e}")
                        try:
                            output = await asyncio.to_thread(
                                repl_tool.invoke,
                                tool_args,
                                config=config
                            )
                        except Exception as e:
                            logger.error(f"Tool execution failed: {e}")
                            output = f"Error executing python_repl: {e}"
                    else:
                        output = f"Unsupported tool: {tool_name}"

                    tool_trace.append(f"{tool_name} -> {output}")
                    tool_call_id = tool_call.get("id") or tool_call.get("tool_call_id") or tool_name or "python_repl"
                    messages.append(ToolMessage(content=str(output), tool_call_id=tool_call_id))

                    if output:
                        log_block = f"\n# Run {round_index + 1}\n{output}\n"
                        try:
                            await _dispatch_text_delta(
                                "data-analyst-log-delta",
                                artifact_id,
                                log_block,
                                config
                            )
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
            content_json = result.model_dump_json()
            result_summary = result.execution_summary
            # Mark as error if summary suggests failure
            lowered = (result_summary or "").lower()
            is_error = "error" in lowered or "失敗" in lowered or "エラー" in lowered
            artifact_preview_urls = _extract_preview_urls(result)
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
            analysis_report = "## 実行ログ\n"
            if tool_trace:
                analysis_report += "\n".join([f"- {line}" for line in tool_trace])
            else:
                analysis_report += "- ツール実行なし\n"
            analysis_report += "\n\n## エラー概要\n"
            analysis_report += error_summary or "不明なエラーが発生しました。"

            fallback = DataAnalystOutput(
                execution_summary=f"Error: {error_summary or 'Invalid output'}",
                analysis_report=analysis_report,
                output_files=[],
                blueprints=[],
                visualization_code=None,
                data_sources=[]
            )
            content_json = fallback.model_dump_json()
            result_summary = fallback.execution_summary
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
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"
        is_error = True
        artifact_preview_urls = []
        try:
            await adispatch_custom_event(
                "data-analyst-output",
                {
                    "artifact_id": artifact_id,
                    "output": {
                        "execution_summary": result_summary,
                        "analysis_report": str(e),
                        "output_files": [],
                        "blueprints": [],
                        "visualization_code": None,
                        "data_sources": []
                    },
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
