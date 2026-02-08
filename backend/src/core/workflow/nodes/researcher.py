import logging
import json
import re
from typing import Literal, Any
from urllib.parse import urlparse, urlunparse

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command, Send
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.llm import get_llm_by_type
from src.shared.config.settings import settings
from src.resources.prompts.template import load_prompt_markdown
from src.shared.schemas import (
    ResearchTask,
    ResearchResult,
    ResearchTaskList
)
from src.core.workflow.state import ResearchSubgraphState
from .common import _update_artifact, run_structured_output

logger = logging.getLogger(__name__)

IMAGE_REQUEST_KEYWORDS = (
    "画像",
    "写真",
    "イラスト",
    "参照画像",
    "image",
    "photo",
    "illustration",
    "reference image",
)


def _contains_explicit_image_request(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in text or keyword in lowered for keyword in IMAGE_REQUEST_KEYWORDS)


def _normalize_task_modes_by_instruction(
    tasks: list[ResearchTask],
    instruction_text: str,
) -> list[ResearchTask]:
    explicit_image = _contains_explicit_image_request(instruction_text)
    normalized: list[ResearchTask] = []
    has_image_mode = False

    for task in tasks:
        mode = str(getattr(task, "search_mode", "text_search") or "text_search")
        if mode not in {"text_search", "image_search", "hybrid_search"}:
            mode = "text_search"

        if not explicit_image and mode in {"image_search", "hybrid_search"}:
            mode = "text_search"
        if explicit_image and mode in {"image_search", "hybrid_search"}:
            has_image_mode = True

        normalized.append(task.model_copy(update={"search_mode": mode}))

    if explicit_image and normalized and not has_image_mode:
        normalized[0] = normalized[0].model_copy(update={"search_mode": "image_search"})

    return normalized


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


def _build_image_candidates(urls: list[str], search_mode: str) -> list[dict]:
    if search_mode not in {"image_search", "hybrid_search"}:
        return []

    def normalize_source_url(url: str) -> str:
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                return url
            return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        except Exception:
            return url

    def infer_license_note(url: str) -> str:
        lowered = url.lower()
        if "commons.wikimedia.org" in lowered or "wikipedia.org" in lowered:
            return "Likely CC BY-SA on Wikimedia. Verify the file detail page."
        if "unsplash.com" in lowered or "images.unsplash.com" in lowered:
            return "Unsplash License likely applies. Verify asset page terms."
        if "pexels.com" in lowered or "images.pexels.com" in lowered:
            return "Pexels License likely applies. Verify asset page terms."
        if "pixabay.com" in lowered or "cdn.pixabay.com" in lowered:
            return "Pixabay License likely applies. Verify asset page terms."
        if "flickr.com" in lowered or "staticflickr.com" in lowered:
            return "Flickr image: check photographer-selected license on source page."
        if "githubusercontent.com" in lowered or "raw.githubusercontent.com" in lowered:
            return "Repository license may apply. Verify repository LICENSE and asset rights."
        if re.search(r"\bcc\b|\bcreativecommons\b", lowered):
            return "Creative Commons reference detected in URL. Verify specific CC variant."
        return "License unknown. Manual verification required before use."

    def infer_caption(url: str) -> str:
        try:
            hostname = urlparse(url).netloc
            return f"Image candidate from {hostname}" if hostname else "Image candidate"
        except Exception:
            return "Image candidate"

    candidates: list[dict] = []
    for url in urls:
        lowered = url.lower()
        is_image_like = (
            lowered.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
            or "/image" in lowered
            or "images" in lowered
            or "img" in lowered
            or "photo" in lowered
        )
        if not is_image_like:
            continue
        candidates.append(
            {
                "image_url": url,
                "source_url": normalize_source_url(url),
                "license_note": infer_license_note(url),
                "provider": "grounded_web",
                "caption": infer_caption(url),
                "relevance_score": None,
            }
        )
    return candidates

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
    
    try:
        # 1. Dispatch Start Event
        await adispatch_custom_event(
            "research_worker_start",
            {"task_id": task.id, "perspective": task.perspective},
            config=config
        )

        system_prompt = load_prompt_markdown("researcher")
        
        search_mode = str(getattr(task, "search_mode", "text_search") or "text_search")
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
        
        async for chunk in llm.astream(messages, config=stream_config):
            # Dispatch Token Event
            if chunk.content:
                text_chunk = _extract_text_from_content(chunk.content)
                if not text_chunk:
                    continue
                full_content += text_chunk
                await adispatch_custom_event(
                    "research_worker_token",
                    {"task_id": task.id, "token": text_chunk},
                    config=config
                )

        sources = _extract_urls(full_content)
        image_candidates = _build_image_candidates(sources, search_mode)
        top_image_candidates = image_candidates[:8]

        result = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=full_content,
            sources=sources,
            image_candidates=top_image_candidates,
            confidence=0.9
        )
        
        # [Decentralized Reporting] Emit individual results immediately
        summary_text = f"【{task.perspective}】の調査が完了しました。"
        if image_candidates:
            summary_text += f" 画像候補 {len(image_candidates)} 件を抽出しました。"
        artifact_id = f"step_{step_id}_research_{task.id}"

        if search_mode in {"image_search", "hybrid_search"}:
            await adispatch_custom_event(
                "data-image-search-results",
                {
                    "artifact_id": artifact_id,
                    "task_id": task.id,
                    "query": task.query_hints[0] if task.query_hints else task.perspective,
                    "perspective": task.perspective,
                    "candidates": top_image_candidates,
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
            "artifacts": _update_artifact(state, artifact_id, result.model_dump_json(exclude_none=True)),
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
                        "preview_urls": [c["image_url"] for c in top_image_candidates],
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
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step.get("status") == "in_progress"
            and step.get("capability") == "researcher"
        )
    except StopIteration:
        logger.error("Research Manager called but no in_progress step found.")
        return Command(goto=END, update={})
        
    internal_tasks = state.get("internal_research_tasks", [])
    results = state.get("internal_research_results", [])
    current_idx = state.get("current_task_index", 0)
    completed_task_ids = set()
    for result in results:
        if hasattr(result, "task_id"):
            completed_task_ids.add(result.task_id)
        elif isinstance(result, dict) and "task_id" in result:
            completed_task_ids.add(result["task_id"])

    if not state.get("is_decomposed"):
        logger.info("Manager: Decomposing research step...")
        clear_update = {"internal_research_results": []}
        
        base_prompt = load_prompt_markdown("research_topic_analyzer")
        step_instruction = str(current_step.get("instruction") or "")
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
            tasks = _normalize_task_modes_by_instruction(qa_result.tasks, step_instruction)
            if not tasks:
                 raise ValueError("No tasks generated")
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Fallback to single task.")
            tasks = [
                ResearchTask(
                   id=1, 
                   perspective="General Investigation", 
                   search_mode="text_search",
                   query_hints=[], 
                   priority="high", 
                   expected_output="Detailed report."
                )
            ]

        logger.info(f"Manager: Decomposition complete. {len(tasks)} tasks generated.")
        # [Serialization] Start sequential execution from the first task
        first_task = tasks[0]
        return Command(
            goto=Send("research_worker", {"task": first_task, "step_id": current_step["id"]}),
            update={
                "internal_research_tasks": tasks,
                "is_decomposed": True,
                "current_task_index": 1,  # Next task index
                **clear_update
            }
        )

    # If already decomposed, check if there are more tasks to run
    if current_idx < len(internal_tasks):
        while current_idx < len(internal_tasks):
            next_task = internal_tasks[current_idx]
            next_task_id = next_task.id if hasattr(next_task, "id") else next_task.get("id")
            if next_task_id in completed_task_ids:
                logger.info(f"Manager: Skipping already completed task {next_task_id}")
                current_idx += 1
                continue
            break

    if current_idx < len(internal_tasks):
        logger.info(f"Manager: Dispatching next task ({current_idx + 1}/{len(internal_tasks)})")
        next_task = internal_tasks[current_idx]
        return Command(
            goto=Send("research_worker", {"task": next_task, "step_id": current_step["id"]}),
            update={
                "current_task_index": current_idx + 1
            }
        )

    # Check if all workers finished (safety check, though in sequential it should be true here)
    if len(results) >= len(internal_tasks) and len(internal_tasks) > 0:
        logger.info("Manager: All workers finished. Finalizing step.")
        
        summary_text = f"計 {len(results)} 件の個別調査が完了しました。"
        current_step["result_summary"] = summary_text

        logger.info(f"Research Manager finished. Finalized {len(results)} individual results.")
        
        return Command(
            goto=END,
            update={
                "artifacts": _update_artifact(state, f"step_{current_step['id']}_research", summary_text),
                "internal_research_tasks": [], 
                "internal_research_results": [],
                "is_decomposed": False,
                # Clear index for next potential research step
                "current_task_index": 0,
                "plan": state["plan"]
            }
        )
    
    logger.info(f"Manager: Waiting for results (Sequential). {len(results)}/{len(internal_tasks)} completed.")
    return Command(goto=END) # Should not reach here in normal sequential flow


def build_researcher_subgraph():
    """Builds the encapsulated researcher subgraph."""
    workflow = StateGraph(ResearchSubgraphState)
    
    workflow.add_node("manager", research_manager_node)
    workflow.add_node("research_worker", research_worker_node)
    
    workflow.add_edge(START, "manager")
    # In sequential flow, worker always returns to manager to check for next task
    workflow.add_edge("research_worker", "manager")
    
    return workflow.compile()
