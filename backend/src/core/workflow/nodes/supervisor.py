import logging
import json
from typing import Literal

from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage, HumanMessage, RemoveMessage
from langchain_core.callbacks.manager import adispatch_custom_event

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.core.workflow.state import State
from src.core.workflow.step_v2 import plan_steps_for_ui

logger = logging.getLogger(__name__)

MAX_MESSAGES = 40
KEEP_LAST_MESSAGES = 10
MAX_ARTIFACTS = 20
CAPABILITY_TO_DESTINATION = {
    "writer": "writer",
    "researcher": "researcher",
    "visualizer": "visualizer",
    "data_analyst": "data_analyst",
}

def _normalize_plan_statuses(plan: list[dict]) -> None:
    """Normalize statuses in-place to canonical values."""
    for step in plan:
        status = step.get("status")
        if status not in {"pending", "in_progress", "completed", "blocked"}:
            step["status"] = "pending"


def _looks_like_error_text(text: str | None) -> bool:
    if not isinstance(text, str):
        return False
    lowered = text.lower()
    return "error" in lowered or "失敗" in text or "エラー" in text or "failed" in lowered


def _resolve_worker_destination(step: dict) -> str | None:
    capability = step.get("capability")
    if isinstance(capability, str):
        return CAPABILITY_TO_DESTINATION.get(capability)
    return None


def _artifact_suffix_for_step(step: dict) -> str:
    capability = step.get("capability")
    if capability == "writer":
        return "story"
    if capability == "visualizer":
        return "visual"
    if capability == "researcher":
        return "research"
    if capability == "data_analyst":
        return "data"
    return "output"


def _extract_failure_metadata(current_step: dict, artifact_value: object) -> tuple[bool, list[str], str | None]:
    failed = False
    failed_checks: list[str] = []
    notes: str | None = None

    result_summary = current_step.get("result_summary")
    if _looks_like_error_text(result_summary if isinstance(result_summary, str) else None):
        failed = True
        notes = result_summary if isinstance(result_summary, str) else notes

    if artifact_value is None:
        if failed and not failed_checks:
            failed_checks = ["worker_execution"]
        return failed, failed_checks, notes

    parsed = artifact_value
    if isinstance(artifact_value, str):
        if _looks_like_error_text(artifact_value):
            failed = True
            notes = artifact_value
        try:
            parsed = json.loads(artifact_value)
        except Exception:
            parsed = artifact_value

    if isinstance(parsed, dict):
        if parsed.get("error"):
            failed = True
            notes = str(parsed.get("notes") or parsed.get("error"))
        raw_checks = parsed.get("failed_checks")
        if isinstance(raw_checks, list):
            failed_checks.extend(str(item) for item in raw_checks if isinstance(item, str))
        execution_summary = parsed.get("execution_summary")
        if _looks_like_error_text(execution_summary if isinstance(execution_summary, str) else None):
            failed = True
            if not notes and isinstance(execution_summary, str):
                notes = execution_summary
        analysis_report = parsed.get("analysis_report")
        if _looks_like_error_text(analysis_report if isinstance(analysis_report, str) else None):
            failed = True
            if not notes and isinstance(analysis_report, str):
                notes = analysis_report

    if failed and not failed_checks:
        failed_checks = ["worker_execution"]
    failed_checks = sorted(set(failed_checks))
    return failed, failed_checks, notes

def _merge_updates(*updates: dict) -> dict:
    """Merge update dicts while concatenating messages."""
    merged: dict = {}
    for update in updates:
        if not update:
            continue
        for key, value in update.items():
            if key == "messages":
                merged.setdefault("messages", []).extend(value)
            elif key == "artifacts":
                prev = merged.get("artifacts", {})
                merged["artifacts"] = {**prev, **value}
            else:
                merged[key] = value
    return merged

def _format_messages_for_summary(messages: list) -> str:
    lines = []
    for m in messages:
        if getattr(m, "type", None) in ("human", "ai", "system"):
            lines.append(f"{m.type}: {m.content}")
    return "\n".join(lines)

async def _compact_state_if_needed(state: State, config: RunnableConfig) -> dict | None:
    """Summarize and delete old messages using RemoveMessage."""
    try:
        messages = state.get("messages", [])
        if len(messages) <= MAX_MESSAGES:
            return None

        old_messages = messages[:-KEEP_LAST_MESSAGES]
        removable = [m for m in old_messages if getattr(m, "id", None)]
        if not removable:
            return None

        summary_source = _format_messages_for_summary(old_messages)
        if not summary_source:
            return None

        previous_summary = state.get("summary") or ""
        prompt = (
            "Summarize the following conversation briefly in Japanese, focusing on "
            "user intent, decisions, and produced artifacts.\n\n"
            f"Existing summary (if any):\n{previous_summary}\n\n"
            f"New conversation to summarize:\n{summary_source}"
        )

        llm = get_llm_by_type("basic")
        stream_config = config.copy()
        stream_config["run_name"] = "supervisor_summarizer"

        summary_response = await llm.ainvoke([SystemMessage(content=prompt)], config=stream_config)
        summary_text = (summary_response.content or "").strip()
        if not summary_text:
            return None

        # Remove any prior summary messages that are old enough to be in the removable set
        removal_ids = {
            m.id
            for m in old_messages
            if getattr(m, "id", None) and getattr(m, "name", "") == "summary"
        }
        removal_ids.update({m.id for m in removable})
        remove_ops = [RemoveMessage(id=mid) for mid in removal_ids]

        return {
            "messages": remove_ops + [
                SystemMessage(content=f"Conversation Summary:\n{summary_text}", name="summary")
            ],
            "summary": summary_text
        }
    except Exception as e:
        logger.warning(f"State compaction failed: {e}")
        return None

def _prune_artifacts_if_needed(state: State) -> dict | None:
    """Remove oldest artifacts by setting value=None (see reducer)."""
    artifacts = state.get("artifacts", {})
    if len(artifacts) <= MAX_ARTIFACTS:
        return None
    keys = list(artifacts.keys())
    to_remove = keys[:-MAX_ARTIFACTS]
    if not to_remove:
        return None
    return {"artifacts": {k: None for k in to_remove}}

async def _generate_supervisor_report(state: State, config: RunnableConfig, is_final: bool = False) -> str:
    """Generate a dynamic status report using the basic LLM."""
    try:
        plan = state.get("plan", [])
        _normalize_plan_statuses(plan)
        
        prompt_name = "supervisor"
        enriched_state = state.copy()

        if is_final:
            prompt_name = "supervisor_final"
            # Summarize plan
            plan_lines = []
            for step in plan:
                status_emoji = "✅" if step.get("status") == "completed" else "⏳"
                plan_lines.append(f"- {status_emoji} {step.get('title')}: {step.get('result_summary', '完了')}")
            enriched_state["PLAN_SUMMARY"] = "\n".join(plan_lines)
            
            # Summarize artifacts (just keys/types to avoid token bloom)
            artifacts = state.get("artifacts", {})
            artifact_keys = [k for k in artifacts.keys() if artifacts[k] is not None]
            enriched_state["ARTIFACTS_SUMMARY"] = ", ".join(artifact_keys) if artifact_keys else "なし"
        else:
            # Identify last achievement
            last_step = None
            for step in reversed(plan):
                if step.get("status") == "completed":
                    last_step = step
                    break
            
            # Identify next objective
            next_step = None
            for step in plan:
                if step.get("status") == "in_progress":
                    next_step = step
                    break
            
            # Default fallback values
            last_achievement = "制作の準備と計画の立案"
            if last_step:
                summary = last_step.get("result_summary") or last_step.get("description", "")
                last_achievement = f"{last_step.get('title', '前の工程')}: {summary}"
                
            next_objective = "全体構成の検討"
            if next_step:
                next_objective = f"{next_step.get('title', '次の工程')}: {next_step.get('instruction', '')}"

            # Enrich state with context variables for the prompt
            enriched_state["LAST_ACHIEVEMENT"] = last_achievement
            enriched_state["NEXT_OBJECTIVE"] = next_objective

        # Generate messages using only the specific context (no message history)
        # to prevent the "basic" model from hallucinating or summarizing the entire plan.
        # Use HumanMessage because Gemini API requires at least one user-role message.
        messages = [HumanMessage(content=apply_prompt_template(prompt_name, enriched_state)[0].content)]
        # Use basic model for status reports to save cost/latency
        llm = get_llm_by_type("basic")
        
        # Use astream to ensure events are emitted
        response_content = ""
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "supervisor"
        
        async for chunk in llm.astream(messages, config=stream_config):
            if chunk.content:
                if isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and "text" in part:
                            response_content += part["text"]
                        elif isinstance(part, str):
                            response_content += part
                else:
                    response_content += str(chunk.content)
            
        return response_content
    except Exception as e:
        logger.error(f"Failed to generate supervisor report: {e}")
        return "進捗を確認しました。引き続き制作を進めてまいりますね。"

async def _dispatch_plan_update(plan: list[dict], config: RunnableConfig) -> None:
    """Emit the latest plan to the frontend."""
    try:
        await adispatch_custom_event(
            "plan_update",
            {
                "plan": plan_steps_for_ui(plan),
                "ui_type": "plan_update",
                "title": "Execution Plan",
                "description": "The updated execution plan."
            },
            config=config
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan update: {e}")


async def _dispatch_plan_step_started(step: dict, config: RunnableConfig) -> None:
    """Emit step-start event for timeline grouping."""
    try:
        await adispatch_custom_event(
            "data-plan_step_started",
            {
                "step_id": step.get("id"),
                "title": step.get("title"),
                "status": "in_progress",
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan step started: {e}")


async def _dispatch_plan_step_ended(step: dict, status: str, config: RunnableConfig) -> None:
    """Emit step-end event for timeline grouping."""
    try:
        await adispatch_custom_event(
            "data-plan_step_ended",
            {
                "step_id": step.get("id"),
                "title": step.get("title"),
                "status": status,
            },
            config=config,
        )
    except Exception as e:
        logger.warning(f"Failed to dispatch plan step ended: {e}")

async def supervisor_node(state: State, config: RunnableConfig) -> Command:
    """
    Supervisor Node (Orchestrator).
    """
    logger.info("Supervisor evaluating state")
    
    plan = state.get("plan", [])
    _normalize_plan_statuses(plan)
    
    current_step_index = -1
    current_step = None
    
    # Check for in-progress step
    for i, step in enumerate(plan):
        if step.get("status") == "in_progress":
            current_step_index = i
            current_step = step
            break
            
    # If no step is in progress, find the first pending step
    if current_step is None:
        for i, step in enumerate(plan):
            if step.get("status") == "pending":
                current_step_index = i
                current_step = step
                break
    
    if current_step is None:
        logger.info("All steps completed. Generating final report.")
        
        # Check if we've already sent the final report to avoid duplication
        # We can use a custom flag in messages or just rely on the fact that this is the last call.
        report = await _generate_supervisor_report(state, config, is_final=True)
        
        return Command(
            goto="__end__",
            update={"messages": [AIMessage(content=report, name="supervisor")]}
        )
        
    destination = _resolve_worker_destination(current_step)
    
    if current_step.get("status") == "in_progress":
        suffix = _artifact_suffix_for_step(current_step)
        artifact_key = f"step_{current_step['id']}_{suffix}"
        
        artifacts = state.get("artifacts", {})
        step_completed = artifact_key in artifacts
        
        if step_completed:
            artifact_value = artifacts.get(artifact_key)
            failed, failed_checks, failure_notes = _extract_failure_metadata(current_step, artifact_value)
            if failed:
                plan[current_step_index]["status"] = "blocked"
                await _dispatch_plan_step_ended(current_step, "blocked", config)
                quality_reports = dict(state.get("quality_reports", {}) or {})
                step_id = current_step.get("id")
                if isinstance(step_id, int):
                    quality_reports[step_id] = {
                        "step_id": step_id,
                        "passed": False,
                        "failed_checks": failed_checks,
                        "notes": failure_notes or current_step.get("result_summary") or "Worker output indicates failure.",
                    }
                logger.warning(
                    "Step %s (%s) marked blocked due to failure artifact.",
                    current_step_index,
                    destination or "unknown",
                )
                return Command(
                    goto="retry_or_alt_mode",
                    update={"plan": plan, "quality_reports": quality_reports},
                )

            plan[current_step_index]["status"] = "completed"
            await _dispatch_plan_step_ended(current_step, "completed", config)
            logger.info(f"Step {current_step_index} ({destination or 'unknown'}) completed. Marking as completed.")

            await _dispatch_plan_update(plan, config)
            
            # Generate report after completion
            report = await _generate_supervisor_report(state, config)

            compact_update = await _compact_state_if_needed(state, config)
            prune_update = _prune_artifacts_if_needed(state)

            return Command(
                goto="supervisor",
                update=_merge_updates(
                    {"plan": plan, "messages": [AIMessage(content=report, name="supervisor")]},
                    compact_update,
                    prune_update
                )
            )
        else:
             if destination is None:
                 logger.error(f"Step {current_step_index} has no resolvable destination.")
                 plan[current_step_index]["status"] = "blocked"
                 return Command(
                     goto="retry_or_alt_mode",
                     update={"plan": plan}
                 )
             logger.info(f"Step {current_step_index} ({destination}) in progress but no artifact. Re-assigning.")
             return Command(goto=destination)

    elif current_step.get("status") == "pending":
        if destination is None:
            logger.error(f"Pending step {current_step_index} has no resolvable destination.")
            plan[current_step_index]["status"] = "blocked"
            return Command(
                goto="retry_or_alt_mode",
                update={"plan": plan}
            )

        logger.info(f"Starting Step {current_step_index} ({destination})")
        
        plan[current_step_index]["status"] = "in_progress"
        await _dispatch_plan_step_started(current_step, config)

        await _dispatch_plan_update(plan, config)
        
        # Generate report for next step
        report = await _generate_supervisor_report(state, config)

        compact_update = await _compact_state_if_needed(state, config)
        prune_update = _prune_artifacts_if_needed(state)

        return Command(
            goto=destination,
            update=_merge_updates(
                {"plan": plan, "messages": [AIMessage(content=report, name="supervisor")]},
                compact_update,
                prune_update
            )
        )
        
    return Command(goto="__end__")
