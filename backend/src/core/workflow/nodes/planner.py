import logging
import json
from copy import deepcopy
from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import PlannerOutput
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

async def planner_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node - uses structured output for reliable JSON execution plan."""
    logger.info("Planner creating execution plan")
    
    context_state = deepcopy(state)
    context_state["plan"] = json.dumps(state.get("plan", []), ensure_ascii=False, indent=2)
    
    messages = apply_prompt_template("planner", context_state)
    
    llm = get_llm_by_type("reasoning")
    
    try:
        # Use with_structured_output explicitly for Pydantic parsing reliability
        structured_llm = llm.with_structured_output(PlannerOutput)
        planner_output: PlannerOutput = await structured_llm.ainvoke(messages)
        
        logger.debug(f"Planner Output: {planner_output}")
        plan_data = [step.model_dump() for step in planner_output.steps]
        
        logger.info(f"Plan generated with {len(plan_data)} steps.")

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
        logger.error(f"Planner structured output failed: {e}")
        return Command(
            update={"messages": [AIMessage(content=f"Failed to generate a valid plan: {e}", name="planner")]},
            goto="__end__"
        )
