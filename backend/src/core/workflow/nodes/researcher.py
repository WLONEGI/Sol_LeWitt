import asyncio
import hashlib
import json
import logging
import mimetypes
import re
import uuid
from typing import Literal, Any
from urllib.parse import urlparse, urlunparse

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langgraph.types import Command, Send
from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from src.infrastructure.llm.llm import get_llm_by_type
from src.infrastructure.storage.gcs import download_blob_as_bytes, upload_to_gcs
from src.resources.prompts.template import load_prompt_markdown
from src.shared.schemas import (
    ResearchTask,
    ResearchResult,
    ResearchTaskList
)
from src.core.workflow.state import ResearchSubgraphState
from .common import _update_artifact, run_structured_output

logger = logging.getLogger(__name__)
VALID_SEARCH_MODES = {"text_search", "image_search", "hybrid_search"}
MAX_IMAGE_CANDIDATES = 10
IMAGE_EXT_TO_MIME: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
MIME_TO_IMAGE_EXT: dict[str, str] = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}

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


def _normalize_search_mode(value: Any, default: str | None = "text_search") -> str | None:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in VALID_SEARCH_MODES:
            return normalized
    return default if default in VALID_SEARCH_MODES else None


def _normalize_task_modes_by_instruction(
    tasks: list[ResearchTask],
    instruction_text: str,
    preferred_mode: str | None = None,
) -> list[ResearchTask]:
    explicit_image = _contains_explicit_image_request(instruction_text)
    preferred = _normalize_search_mode(preferred_mode, default=None)
    normalized: list[ResearchTask] = []
    has_image_mode = False

    for task in tasks:
        mode = _normalize_search_mode(getattr(task, "search_mode", "text_search"), default="text_search") or "text_search"

        if preferred == "text_search":
            mode = "text_search"
        elif preferred == "image_search":
            if mode == "text_search":
                mode = "image_search"
        elif preferred == "hybrid_search":
            if mode == "text_search" and explicit_image:
                mode = "hybrid_search"
        elif not explicit_image and mode in {"image_search", "hybrid_search"}:
            mode = "text_search"

        if mode in {"image_search", "hybrid_search"}:
            has_image_mode = True

        normalized.append(task.model_copy(update={"search_mode": mode}))

    if normalized and not has_image_mode:
        if preferred in {"image_search", "hybrid_search"}:
            normalized[0] = normalized[0].model_copy(update={"search_mode": preferred})
        elif explicit_image:
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


def _sanitize_filename(text: str) -> str:
    value = re.sub(r"[^\w\s.-]", "", text).strip()
    value = value.replace(" ", "_")
    return value[:80] or "research"


def _infer_image_extension(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    path = parsed.path.lower()
    ext = ""
    for candidate_ext in IMAGE_EXT_TO_MIME.keys():
        if path.endswith(candidate_ext):
            ext = candidate_ext
            break
    if not ext:
        guessed_mime, _ = mimetypes.guess_type(path)
        if isinstance(guessed_mime, str) and guessed_mime in MIME_TO_IMAGE_EXT:
            ext = MIME_TO_IMAGE_EXT[guessed_mime]
    if not ext:
        ext = ".png"
    return ext, IMAGE_EXT_TO_MIME.get(ext, "image/png")


async def _store_image_candidates_to_gcs(
    *,
    candidates: list[dict],
    session_id: str,
    safe_step_title: str,
    step_id: str | int,
    task_id: str | int,
) -> list[dict]:
    stored: list[dict] = []
    seen_hashes: set[str] = set()

    for index, candidate in enumerate(candidates[:MAX_IMAGE_CANDIDATES], start=1):
        image_url = str(candidate.get("image_url") or "").strip()
        if not image_url:
            continue

        try:
            payload = await asyncio.to_thread(download_blob_as_bytes, image_url)
            if not payload:
                continue

            digest = hashlib.sha256(payload).hexdigest()
            if digest in seen_hashes:
                continue
            seen_hashes.add(digest)

            ext, content_type = _infer_image_extension(image_url)
            object_name = (
                f"generated_assets/{session_id}/{safe_step_title}/research/"
                f"step_{step_id}/task_{task_id}/{index:02d}_{digest[:12]}{ext}"
            )
            uploaded_url = await asyncio.to_thread(
                upload_to_gcs,
                payload,
                content_type,
                None,
                None,
                object_name,
            )
            stored.append(
                {
                    "task_id": task_id,
                    "source_url": candidate.get("source_url"),
                    "image_url": image_url,
                    "gcs_url": uploaded_url,
                    "sha256": digest,
                    "content_type": content_type,
                    "license_note": candidate.get("license_note"),
                    "caption": candidate.get("caption"),
                }
            )
        except Exception as image_err:
            logger.warning("Failed to store image candidate %s: %s", image_url, image_err)
            continue

    return stored

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
    
    step_title = str(state.get("step_title") or "research")
    step_mode = _normalize_search_mode(state.get("step_mode"), default=None)
    session_id = str(config.get("configurable", {}).get("thread_id") or uuid.uuid4())
    safe_step_title = _sanitize_filename(step_title)

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
        top_image_candidates = image_candidates[:MAX_IMAGE_CANDIDATES]
        stored_images: list[dict] = []
        if search_mode in {"image_search", "hybrid_search"} and top_image_candidates:
            try:
                stored_images = await _store_image_candidates_to_gcs(
                    candidates=top_image_candidates,
                    session_id=session_id,
                    safe_step_title=safe_step_title,
                    step_id=step_id,
                    task_id=task.id,
                )
            except Exception as image_store_err:
                logger.warning("Failed to persist image candidates for task %s: %s", task.id, image_store_err)

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
        if search_mode in {"image_search", "hybrid_search"}:
            summary_text += (
                f" 画像候補 {len(top_image_candidates)} 件を抽出し、"
                f"{len(stored_images)} 件を保存しました。"
            )
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
            "artifacts": _update_artifact(
                state,
                artifact_id,
                json.dumps(
                    {
                        **result.model_dump(exclude_none=True),
                        "search_mode": search_mode,
                        "stored_images": stored_images,
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
            if not tasks:
                 raise ValueError("No tasks generated")
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Fallback to single task.")
            fallback_mode = step_mode or ("image_search" if _contains_explicit_image_request(step_instruction) else "text_search")
            tasks = [
                ResearchTask(
                   id=1, 
                   perspective="General Investigation", 
                   search_mode=fallback_mode,
                   query_hints=[], 
                   priority="high", 
                   expected_output="Detailed report."
                )
            ]

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
    if len(results) >= len(internal_tasks) and len(internal_tasks) > 0:
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
