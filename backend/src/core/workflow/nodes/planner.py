import logging
import json
from copy import deepcopy
from typing import Literal

from langchain_core.callbacks import adispatch_custom_event
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import PlannerOutput
from src.core.workflow.state import State
from .common import run_structured_output

logger = logging.getLogger(__name__)

async def planner_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node - uses structured output for reliable JSON execution plan."""
    logger.info("Planner creating execution plan")
    
    context_state = deepcopy(state)
    context_state["plan"] = json.dumps(state.get("plan", []), ensure_ascii=False, indent=2)
    
    messages = apply_prompt_template("planner", context_state)
    logger.debug(f"[DEBUG] Planner Input Messages: {messages}")
    
    llm = get_llm_by_type("reasoning", streaming=True)
    
    try:
        logger.info("Planner: Calling LLM for structured output (streaming=True)")
        
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "planner"
        
        planner_output: PlannerOutput = await run_structured_output(
            llm=llm,
            schema=PlannerOutput,
            messages=messages,
            config=stream_config,
            repair_hint="Schema: PlannerOutput. No extra text."
        )
        
        logger.debug(f"[DEBUG] Planner Output: {planner_output}")
        plan_data = [step.model_dump() for step in planner_output.steps]
        
        logger.info(f"Plan generated successfully with {len(plan_data)} steps.")
        
        # Emit custom event for UI updates since we disabled streaming
        await adispatch_custom_event(
            "plan_updated",
            {
                "plan": plan_data, 
                "ui_type": "plan_update", 
                "title": "Execution Plan", 
                "description": "The updated execution plan."
            },
            config=config
        )

        return Command(
            update={
                "messages": [
                    AIMessage(
                        content="Plan Created",
                        additional_kwargs={
                            "ui_type": "plan_update",
                            "plan": plan_data,
                            "title": "Execution Plan",
                            "description": "The updated execution plan."
                        },
                        name="planner_ui"
                    )
                ],
                "plan": plan_data,
                "artifacts": {}
            },
            goto="supervisor",
        )
    except Exception as e:
        logger.error(f"[CRITICAL] Planner structured output failed. Error type: {type(e).__name__}, Message: {e}")
        # If possible, we'd want raw output here, but with_structured_output hides it on error.
        # For now, let's just log the context.
        return Command(
            update={"messages": [AIMessage(content=f"プランの生成に失敗しました (形式エラー)。詳細: {e}", name="planner")]},
            goto="__end__"
        )
