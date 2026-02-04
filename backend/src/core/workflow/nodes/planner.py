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
from .common import run_structured_output, extract_first_json, split_content_parts

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
        
        # Stream tokens via on_chat_model_stream; keep final JSON in-buffer
        full_text = ""
        async for chunk in llm.astream(messages, config=stream_config):
            if not getattr(chunk, "content", None):
                continue
            thinking_text, text = split_content_parts(chunk.content)
            if text:
                full_text += text

        try:
            json_text = extract_first_json(full_text) or full_text
            planner_output = PlannerOutput.model_validate_json(json_text)
        except Exception as parse_error:
            logger.warning(f"Planner streaming JSON parse failed: {parse_error}. Falling back to repair.")
            planner_output = await run_structured_output(
                llm=llm,
                schema=PlannerOutput,
                messages=messages,
                config=stream_config,
                repair_hint="Schema: PlannerOutput. No extra text."
            )
        
        logger.debug(f"[DEBUG] Planner Output: {planner_output}")
        plan_data = [step.model_dump() for step in planner_output.steps]
        
        logger.info(f"Plan generated successfully with {len(plan_data)} steps.")
        
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
