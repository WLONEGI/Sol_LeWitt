import asyncio
import json
import logging
import os
import re
from typing import Literal, Any

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command, Send
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.llm import astream_with_retry, get_llm_by_type
from src.resources.prompts.template import load_prompt_markdown
from src.shared.schemas import (
    ResearchTask,
    ResearchResult,
    ResearchTaskList
)
from src.core.workflow.state import ResearchSubgraphState
from .common import _update_artifact, run_structured_output

logger = logging.getLogger(__name__)
VALID_SEARCH_MODES = {"text_search"}
try:
    RESEARCH_TOKEN_FLUSH_CHARS = max(64, int(os.getenv("RESEARCH_TOKEN_FLUSH_CHARS", "256")))
except Exception:
    RESEARCH_TOKEN_FLUSH_CHARS = 256
try:
    RESEARCH_TOKEN_FLUSH_INTERVAL_SEC = float(os.getenv("RESEARCH_TOKEN_FLUSH_INTERVAL_SEC", "0.4"))
except Exception:
    RESEARCH_TOKEN_FLUSH_INTERVAL_SEC = 0.4
RESEARCH_TOKEN_FLUSH_INTERVAL_SEC = max(0.05, min(2.0, RESEARCH_TOKEN_FLUSH_INTERVAL_SEC))
DEFAULT_RESEARCH_PERSPECTIVES = (
    "市場動向・背景データの最新情報",
    "先行事例・ベストプラクティス",
    "実行時に考慮すべきリスク・制約条件",
)


def _normalize_search_mode(value: Any, default: str | None = "text_search") -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_SEARCH_MODES:
            return "text_search"
    return "text_search" if default in VALID_SEARCH_MODES else None


def _normalize_task_modes_by_instruction(
    tasks: list[ResearchTask],
    instruction_text: str,
    preferred_mode: str | None = None,
) -> list[ResearchTask]:
    del instruction_text
    del preferred_mode
    return [task.model_copy(update={"search_mode": "text_search"}) for task in tasks]


def _extract_instruction_perspectives(instruction_text: str) -> list[str]:
    if not instruction_text:
        return []

    lines = [line.strip() for line in instruction_text.splitlines() if line.strip()]
    perspectives: list[str] = []
    in_perspective_section = False

    for line in lines:
        if "調査観点" in line:
            in_perspective_section = True
            continue
        if not in_perspective_section:
            continue
        if "分解" in line and "調査" in line:
            continue

        cleaned = re.sub(r"^(?:[-*・]|[0-9]+[.)、])\s*", "", line).strip()
        if not cleaned:
            continue
        if cleaned not in perspectives:
            perspectives.append(cleaned)
        if len(perspectives) >= 5:
            break

    if perspectives:
        return perspectives

    marker_index = instruction_text.find("調査観点")
    if marker_index < 0:
        return []

    tail = instruction_text[marker_index:]
    for chunk in re.split(r"[、,\n/]", tail):
        cleaned = re.sub(r"^(?:[-*・]|[0-9]+[.)、])\s*", "", chunk).strip()
        if not cleaned or cleaned.startswith("調査観点"):
            continue
        if "分解" in cleaned and "調査" in cleaned:
            continue
        if cleaned not in perspectives:
            perspectives.append(cleaned)
        if len(perspectives) >= 5:
            break
    return perspectives


def _resolve_fallback_perspectives(instruction_text: str) -> list[str]:
    extracted = _extract_instruction_perspectives(instruction_text)
    merged: list[str] = []
    for item in extracted + list(DEFAULT_RESEARCH_PERSPECTIVES):
        normalized = item.strip()
        if not normalized:
            continue
        if normalized in merged:
            continue
        merged.append(normalized)
        if len(merged) >= 3:
            break
    return merged


def _build_fallback_research_tasks(
    instruction_text: str,
    step_mode: str | None,
) -> list[ResearchTask]:
    search_mode = _normalize_search_mode(step_mode, default="text_search") or "text_search"
    perspectives = _resolve_fallback_perspectives(instruction_text)
    tasks: list[ResearchTask] = []

    for idx, perspective in enumerate(perspectives, start=1):
        query_base = perspective.replace("・", " ").strip()
        query_hints = [
            f"{query_base} 最新",
            f"{query_base} 事例",
            f"{query_base} 出典",
        ]
        tasks.append(
            ResearchTask(
                id=idx,
                perspective=perspective,
                search_mode=search_mode,
                query_hints=query_hints[:3],
                priority="high" if idx == 1 else "medium",
                expected_output=f"{perspective}について、主要な事実・根拠・出典URLを整理する",
            )
        )
    return tasks


def _ensure_minimum_task_diversity(
    tasks: list[ResearchTask],
    instruction_text: str,
    step_mode: str | None,
) -> list[ResearchTask]:
    if len(tasks) >= 2:
        return tasks
    return _build_fallback_research_tasks(instruction_text, step_mode)


def _ensure_unique_task_ids(tasks: list[ResearchTask]) -> list[ResearchTask]:
    if not tasks:
        return []

    seen: set[int] = set()
    has_duplicate = False
    for task in tasks:
        if task.id in seen:
            has_duplicate = True
            break
        seen.add(task.id)

    if not has_duplicate:
        return tasks

    logger.warning(
        "Research Manager detected duplicate task IDs. Re-indexing tasks sequentially."
    )
    return [task.model_copy(update={"id": idx}) for idx, task in enumerate(tasks, start=1)]


def _extract_text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text" and isinstance(part.get("text"), str):
                    texts.append(part["text"])
                elif part_type == "thinking":
                    continue
                elif isinstance(part.get("text"), str):
                    texts.append(part["text"])
            elif isinstance(part, str):
                texts.append(part)
        return "".join(texts)
    if isinstance(content, dict):
        text = content.get("text")
        return text if isinstance(text, str) else ""
    return ""


def _extract_urls(text: str) -> list[str]:
    if not text:
        return []
    urls = re.findall(r"https?://[^\s\]\)<>\"']+", text)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in urls:
        cleaned = url.rstrip(".,);")
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            deduped.append(cleaned)
    return deduped


async def research_worker_node(state: ResearchSubgraphState, config: RunnableConfig) -> dict:
    """
    Worker node for executing a single research task.
    """
    from langchain_core.callbacks.manager import adispatch_custom_event

    task_data = state.get("task")
    if not task_data:
        logger.warning("Research Worker received empty task")
        return {"internal_research_results": []}

    if isinstance(task_data, dict):
        try:
            task = ResearchTask.model_validate(task_data)
        except Exception as e:
            logger.error(f"Failed to validate task data: {e}")
            return {"internal_research_results": []}
    else:
        task = task_data

    task_id = getattr(task, "id", "unknown")
    logger.info(f"Worker executing task {task_id}: {task.perspective}")
    
    # Use step_id from state if provided (passed via Send), or fallback to plan search
    step_id = state.get("step_id")
    if not step_id:
        try:
            current_step = next(
                step for step in state.get("plan", []) 
                if step.get("status") == "in_progress"
                and step.get("capability") == "researcher"
            )
            step_id = current_step["id"]
        except (StopIteration, KeyError, TypeError):
            step_id = "unknown"
    
    step_mode = _normalize_search_mode(state.get("step_mode"), default=None)

    try:
        # 1. Dispatch Start Event
        await adispatch_custom_event(
            "research_worker_start",
            {
                "task_id": task.id,
                "perspective": task.perspective,
                "search_mode": _normalize_search_mode(getattr(task, "search_mode", "text_search"), default="text_search"),
            },
            config=config
        )

        system_prompt = load_prompt_markdown("researcher")
        
        task_search_mode = _normalize_search_mode(getattr(task, "search_mode", "text_search"), default="text_search")
        search_mode = step_mode or task_search_mode or "text_search"
        instruction = (
            f"You are investigating: '{task.perspective}'.\n"
            f"Search Mode: {search_mode}\n"
            f"Requirement: {task.expected_output}\n"
        )
        if task.query_hints:
            instruction += f"Suggested Queries: {', '.join(task.query_hints)}"
            
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=instruction, name="dispatcher")
        ]
        
        # Use Grounded LLM (Google Search enabled)
        llm = get_llm_by_type("grounded")
        
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = f"research_worker_{task_id}"
        
        # 2. Stream Tokens
        full_content = ""
        token_buffer = ""
        loop = asyncio.get_running_loop()
        last_token_flush_at = loop.time()

        async def flush_token_buffer(force: bool = False) -> None:
            nonlocal token_buffer, last_token_flush_at
            if not token_buffer:
                return

            now = loop.time()
            if not force:
                has_line_break = "\n" in token_buffer
                should_flush = (
                    len(token_buffer) >= RESEARCH_TOKEN_FLUSH_CHARS
                    or (now - last_token_flush_at) >= RESEARCH_TOKEN_FLUSH_INTERVAL_SEC
                    or has_line_break
                )
                if not should_flush:
                    return

            await adispatch_custom_event(
                "research_worker_token",
                {"task_id": task.id, "token": token_buffer},
                config=config
            )
            token_buffer = ""
            last_token_flush_at = now

        async for chunk in astream_with_retry(
            lambda: llm.astream(messages, config=stream_config),
            operation_name=f"research_worker.{task_id}.astream",
        ):
            # Dispatch Token Event
            if chunk.content:
                text_chunk = _extract_text_from_content(chunk.content)
                if not text_chunk:
                    continue
                full_content += text_chunk
                token_buffer += text_chunk
                await flush_token_buffer()

        await flush_token_buffer(force=True)

        sources = _extract_urls(full_content)

        result = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=full_content,
            sources=sources,
            image_candidates=[],
            confidence=0.9
        )

        # [Decentralized Reporting] Emit individual results immediately
        summary_text = f"【{task.perspective}】の調査が完了しました。"
        artifact_id = f"step_{step_id}_research_{task.id}"

        await adispatch_custom_event(
            "data-research-report",
            {
                "artifact_id": artifact_id,
                "task_id": task.id,
                "perspective": task.perspective,
                "search_mode": search_mode,
                "status": "completed",
                "report": full_content,
                "sources": sources,
            },
            config=config,
        )

        # 3. Dispatch Complete Event
        await adispatch_custom_event(
             "research_worker_complete",
             {"task_id": task.id},
             config=config
        )
        
        return {
            "internal_research_results": [result],
            "artifacts": _update_artifact(
                state,
                artifact_id,
                json.dumps(
                    {
                        **result.model_dump(exclude_none=True),
                        "search_mode": search_mode,
                    },
                    ensure_ascii=False,
                ),
            ),
            "messages": [
                AIMessage(
                    content=summary_text,
                    additional_kwargs={
                        "ui_type": "worker_result",
                        "capability": "researcher",
                        "role": "researcher", 
                        "status": "completed",
                        "result_summary": summary_text
                    },
                    name=f"researcher_{task.id}_ui"
                ),
                AIMessage(
                    content=f"Research Report: {task.perspective}",
                    additional_kwargs={
                        "ui_type": "artifact_view",
                        "artifact_id": artifact_id,
                        "title": f"調査レポート: {task.perspective}",
                        "icon": "BookOpen",
                    },
                    name=f"researcher_{task.id}_artifact"
                )
            ]
        }

    except Exception as e:
        logger.error(f"Research worker {task_id} failed: {e}")
        error_message = f"Research worker failed: {e}"
        try:
            await adispatch_custom_event(
                "data-research-report",
                {
                    "artifact_id": f"step_{step_id}_research_{task.id}",
                    "task_id": task.id,
                    "perspective": task.perspective,
                    "search_mode": _normalize_search_mode(getattr(task, "search_mode", "text_search"), default="text_search"),
                    "status": "failed",
                    "report": error_message,
                    "sources": [],
                },
                config=config,
            )
            await adispatch_custom_event(
                "research_worker_complete",
                {"task_id": task.id, "status": "failed", "error": error_message},
                config=config
            )
        except Exception as dispatch_error:
            logger.error(f"Failed to dispatch research_worker_complete: {dispatch_error}")
        return {
            "internal_research_results": [
                ResearchResult(
                    task_id=task.id,
                    perspective=task.perspective,
                    report=error_message,
                    sources=[],
                    image_candidates=[],
                    confidence=0.0
                )
            ]
        }

async def research_manager_node(state: ResearchSubgraphState, config: RunnableConfig) -> Command[Literal["research_worker", "__end__"]]:
    """
    Manager Node (Orchestrator). 
    Handles decomposition and sequential dispatch of workers.
    """
    logger.info(f"Research Manager active. Decomposed: {state.get('is_decomposed', False)}")

    try:
        _step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step.get("status") == "in_progress"
            and step.get("capability") == "researcher"
        )
    except StopIteration:
        logger.error("Research Manager called but no in_progress step found.")
        return Command(goto=END, update={})
        
    internal_tasks = state.get("internal_research_tasks", [])
    results = state.get("internal_research_results", [])
    current_idx_raw = state.get("current_task_index", 0)
    current_idx = current_idx_raw if isinstance(current_idx_raw, int) else 0
    if current_idx < 0:
        current_idx = 0

    if not state.get("is_decomposed"):
        logger.info("Manager: Decomposing research step...")
        clear_update = {"internal_research_results": []}
        
        base_prompt = load_prompt_markdown("research_topic_analyzer")
        step_instruction = str(current_step.get("instruction") or "")
        step_mode = _normalize_search_mode(current_step.get("mode"), default=None)
        instruction_content = f"User Instruction: {step_instruction}"
        
        llm = get_llm_by_type("reasoning")
        
        try:
            # Prepare messages for the LLM
            messages = [
                SystemMessage(content=base_prompt),
                HumanMessage(content=instruction_content)
            ]
            
            # Add run_name for better visibility in stream events
            stream_config = config.copy()
            stream_config["run_name"] = "researcher"
            
            qa_result: ResearchTaskList = await run_structured_output(
                llm=llm,
                schema=ResearchTaskList,
                messages=messages,
                config=stream_config,
                repair_hint="Schema: ResearchTaskList. No extra text."
            )
            tasks = _normalize_task_modes_by_instruction(
                qa_result.tasks,
                step_instruction,
                preferred_mode=step_mode,
            )
            tasks = _ensure_minimum_task_diversity(tasks, step_instruction, step_mode)
            tasks = _ensure_unique_task_ids(tasks)
            if not tasks:
                 raise ValueError("No tasks generated")
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Fallback to multi-perspective tasks.")
            tasks = _build_fallback_research_tasks(step_instruction, step_mode)
            tasks = _ensure_unique_task_ids(tasks)

        logger.info(f"Manager: Decomposition complete. {len(tasks)} tasks generated.")
        # [Serialization] Start sequential execution from the first task
        first_task = tasks[0]
        return Command(
            goto=Send(
                "research_worker",
                {
                    "task": first_task,
                    "step_id": current_step["id"],
                    "step_title": current_step.get("title") or current_step.get("description") or "research",
                    "step_mode": step_mode,
                },
            ),
            update={
                "internal_research_tasks": tasks,
                "is_decomposed": True,
                "current_task_index": 1,  # Next task index
                **clear_update
            }
        )

    task_count = len(internal_tasks)
    result_count = len(results)
    if result_count > current_idx:
        logger.info(
            "Manager: Advancing current_task_index from %s to %s based on completed results.",
            current_idx,
            result_count,
        )
        current_idx = result_count

    if current_idx < task_count:
        logger.info(f"Manager: Dispatching next task ({current_idx + 1}/{task_count})")
        next_task = internal_tasks[current_idx]
        return Command(
            goto=Send(
                "research_worker",
                {
                    "task": next_task,
                    "step_id": current_step["id"],
                    "step_title": current_step.get("title") or current_step.get("description") or "research",
                    "step_mode": _normalize_search_mode(current_step.get("mode"), default=None),
                },
            ),
            update={
                "current_task_index": current_idx + 1
            }
        )

    # Check if all workers finished (safety check, though in sequential it should be true here)
    if result_count >= task_count and task_count > 0:
        logger.info("Manager: All workers finished. Finalizing step.")

        failed_results = 0
        completed_results = 0
        for result in results:
            confidence = getattr(result, "confidence", None)
            if confidence is None and isinstance(result, dict):
                confidence = result.get("confidence")
            score = float(confidence) if isinstance(confidence, (int, float)) else 0.0
            if score <= 0.0:
                failed_results += 1
            else:
                completed_results += 1

        if failed_results > 0 and completed_results > 0:
            summary_text = f"計 {len(results)} 件中 {completed_results} 件成功、{failed_results} 件失敗で完了しました。"
        elif failed_results > 0:
            summary_text = f"計 {len(results)} 件の調査が失敗しました。"
        else:
            summary_text = f"計 {len(results)} 件の個別調査が完了しました。"
        current_step["result_summary"] = summary_text

        logger.info(f"Research Manager finished. Finalized {len(results)} individual results.")
        
        return Command(
            goto=END,
            update={
                "artifacts": _update_artifact(
                    state,
                    f"step_{current_step['id']}_research",
                    json.dumps(
                        {
                            "summary": summary_text,
                            "total_tasks": len(results),
                            "completed_tasks": completed_results,
                            "failed_tasks": failed_results,
                        },
                        ensure_ascii=False,
                    ),
                ),
                "internal_research_tasks": [], 
                "internal_research_results": [],
                "is_decomposed": False,
                # Clear index for next potential research step
                "current_task_index": 0,
                "plan": state["plan"]
            }
        )
    
    mismatch_message = (
        "Research manager detected inconsistent sequential state. "
        f"results={result_count}, tasks={task_count}, current_task_index={current_idx}."
    )
    logger.error("Manager: %s", mismatch_message)
    current_step["result_summary"] = mismatch_message

    failed_tasks = max(0, task_count - result_count)
    return Command(
        goto=END,
        update={
            "artifacts": _update_artifact(
                state,
                f"step_{current_step['id']}_research",
                json.dumps(
                    {
                        "error": mismatch_message,
                        "notes": mismatch_message,
                        "failed_checks": ["research_manager_state_inconsistent"],
                        "summary": mismatch_message,
                        "total_tasks": task_count,
                        "completed_tasks": result_count,
                        "failed_tasks": failed_tasks,
                    },
                    ensure_ascii=False,
                ),
            ),
            "internal_research_tasks": [],
            "internal_research_results": [],
            "is_decomposed": False,
            "current_task_index": 0,
            "plan": state["plan"],
        },
    )


def build_researcher_subgraph():
    """Builds the encapsulated researcher subgraph."""
    workflow = StateGraph(ResearchSubgraphState)
    
    workflow.add_node("manager", research_manager_node)
    workflow.add_node("research_worker", research_worker_node)
    
    workflow.add_edge(START, "manager")
    # In sequential flow, worker always returns to manager to check for next task
    workflow.add_edge("research_worker", "manager")
    
    return workflow.compile()
