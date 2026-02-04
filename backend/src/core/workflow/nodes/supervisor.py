import logging
from typing import Literal

from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, SystemMessage, RemoveMessage

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.config import TEAM_MEMBERS
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

MAX_MESSAGES = 40
KEEP_LAST_MESSAGES = 10
MAX_ARTIFACTS = 20

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

async def _generate_supervisor_report(state: State, config: RunnableConfig) -> str:
    """Generate a dynamic status report using the basic LLM."""
    try:
        plan = state.get("plan", [])
        
        # Identify last achievement
        last_step = None
        for step in reversed(plan):
            if step["status"] == "complete":
                last_step = step
                break
        
        # Identify next objective
        next_step = None
        for step in plan:
            if step["status"] == "in_progress":
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
        enriched_state = state.copy()
        enriched_state["LAST_ACHIEVEMENT"] = last_achievement
        enriched_state["NEXT_OBJECTIVE"] = next_objective

        # Generate messages using only the specific context (no message history)
        # to prevent the "basic" model from hallucinating or summarizing the entire plan.
        messages = [SystemMessage(content=apply_prompt_template("supervisor", enriched_state)[0].content)]
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

async def supervisor_node(state: State, config: RunnableConfig) -> Command[Literal[*TEAM_MEMBERS, "__end__"]]:
    """
    Supervisor Node (Orchestrator).
    """
    logger.info("Supervisor evaluating state")
    
    plan = state.get("plan", [])
    
    current_step_index = -1
    current_step = None
    
    # Check for in-progress step
    for i, step in enumerate(plan):
        if step["status"] == "in_progress":
            current_step_index = i
            current_step = step
            break
            
    # If no step is in progress, find the first pending step
    if current_step is None:
        for i, step in enumerate(plan):
            if step["status"] == "pending":
                current_step_index = i
                current_step = step
                break
    
    if current_step is None:
        logger.info("All steps completed. Ending workflow.")
        return Command(goto="__end__")
        
    current_role = current_step["role"]
    
    if current_step["status"] == "in_progress":
        role_suffix_map = {
            "storywriter": "story",
            "visualizer": "visual",
            "researcher": "research",
            "data_analyst": "data"
        }
        suffix = role_suffix_map.get(current_role, "output")
        artifact_key = f"step_{current_step['id']}_{suffix}"
        
        artifacts = state.get("artifacts", {})
        step_completed = artifact_key in artifacts
        
        if step_completed:
            plan[current_step_index]["status"] = "complete"
            logger.info(f"Step {current_step_index} ({current_role}) completed. Marking as complete.")
            
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
             logger.info(f"Step {current_step_index} ({current_role}) in progress but no artifact. Re-assigning.")
             return Command(goto=current_role)

    elif current_step["status"] == "pending":
        logger.info(f"Starting Step {current_step_index} ({current_role})")
        
        plan[current_step_index]["status"] = "in_progress"
        
        # Generate report for next step
        report = await _generate_supervisor_report(state, config)

        compact_update = await _compact_state_if_needed(state, config)
        prune_update = _prune_artifacts_if_needed(state)

        return Command(
            goto=current_role,
            update=_merge_updates(
                {"plan": plan, "messages": [AIMessage(content=report, name="supervisor")]},
                compact_update,
                prune_update
            )
        )
        
    return Command(goto="__end__")
