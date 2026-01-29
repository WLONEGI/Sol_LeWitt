import logging
import json
from copy import deepcopy
from typing import Literal

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command

from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import PlannerOutput
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

async def planner_node(state: State) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node - uses structured output for reliable JSON execution plan."""
    logger.info("Planner creating execution plan")
    
    context_state = deepcopy(state)
    context_state["plan"] = json.dumps(state.get("plan", []), ensure_ascii=False, indent=2)
    
    messages = apply_prompt_template("planner", context_state)
    
    llm = get_llm_by_type("reasoning")
    llm_with_tools = llm.bind_tools([PlannerOutput])
    
    try:
        accumulated_args = ""
        
        async for chunk in llm_with_tools.astream(messages):
            if chunk.tool_call_chunks:
                for tool_call_chunk in chunk.tool_call_chunks:
                    if tool_call_chunk.get("args"):
                        partial_args = tool_call_chunk["args"]
                        accumulated_args += partial_args
                        
                        # Dispatch raw partial JSON event
                        from langchain_core.callbacks.manager import adispatch_custom_event
                        await adispatch_custom_event(
                            "planner-partial-json",
                            {"args": accumulated_args, "delta": partial_args},
                            config={"tags": ["planner_partial"]}
                        )

        # Final Parsing
        try:
            parsed_args = json.loads(accumulated_args)
            result = PlannerOutput(**parsed_args)
        except json.JSONDecodeError:
             raise ValueError(f"Failed to parse final JSON from Planner: {accumulated_args[:100]}...")

        logger.info("✅ Planner output validated (streaming).")
        plan_data = [step.model_dump() for step in result.steps]
        
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
