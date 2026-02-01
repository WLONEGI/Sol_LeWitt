import logging
from typing import Literal

from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.config import TEAM_MEMBERS, AGENT_LLM_MAP
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

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

        messages = apply_prompt_template("supervisor", enriched_state)
        # Use basic model for status reports to save cost/latency
        llm = get_llm_by_type("basic")
        
        # Use astream to ensure events are emitted
        response_content = ""
        async for chunk in llm.astream(messages, config=config):
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
            
            return Command(
                goto="supervisor", 
                update={
                    "plan": plan,
                    "messages": [AIMessage(content=report, name="supervisor")]
                } 
            )
        else:
             logger.info(f"Step {current_step_index} ({current_role}) in progress but no artifact. Re-assigning.")
             return Command(goto=current_role)

    elif current_step["status"] == "pending":
        logger.info(f"Starting Step {current_step_index} ({current_role})")
        
        plan[current_step_index]["status"] = "in_progress"
        
        # Generate report for next step
        report = await _generate_supervisor_report(state, config)
            
        return Command(
            goto=current_role,
            update={
                "plan": plan,
                "messages": [AIMessage(content=report, name="supervisor")]
            }
        )
        
    return Command(goto="__end__")

