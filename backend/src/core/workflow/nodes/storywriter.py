import logging
import json
from typing import Literal

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from src.shared.config.settings import settings
from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import StorywriterOutput
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.runnables import RunnableConfig
from src.core.workflow.state import State

from .common import create_worker_response, run_structured_output

logger = logging.getLogger(__name__)

async def storywriter_node(state: State, config: RunnableConfig) -> Command[Literal["visualizer"]]:
    """
    Node for the Storywriter agent.
    
    Generates slide content and proceeds to Supervisor.
    """
    logger.info("Storywriter starting task")

    # Find the current in-progress step for this agent
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "storywriter"
        )
    except StopIteration:
        logger.error("Storywriter called but no in_progress step found.")
        return Command(goto="supervisor", update={})
    
    step_id = f"step_{current_step['id']}"
    
    # Provide context including artifacts
    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"
    
    # Build messages with prompt template
    messages = apply_prompt_template("storywriter", state)
    messages.append(HumanMessage(content=context, name="supervisor"))
    
    llm = get_llm_by_type(AGENT_LLM_MAP["storywriter"])
    
    try:
        # Add run_name for better visibility in stream events
        stream_config = config.copy()
        stream_config["run_name"] = "storywriter"
        
        story_output: StorywriterOutput = await run_structured_output(
            llm=llm,
            schema=StorywriterOutput,
            messages=messages,
            config=stream_config,
            repair_hint="Schema: StorywriterOutput. No extra text."
        )
        
        content_json = story_output.model_dump_json(exclude_none=True)
        result_summary = story_output.execution_summary
        logger.info(f"✅ Storywriter generated {len(story_output.slides)} slides")

        # Emit custom event for Slide Outline approval
        await adispatch_custom_event(
            "slide_outline_updated",
            {
                "slides": [s.model_dump() for s in story_output.slides],
                "ui_type": "slide_outline",
                "title": "Slide Outline",
                "description": "The generated slide outline and narrative map."
            },
            config=config
        )
        
        # Update result summary in plan
        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="storywriter",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step['id'],
            state=state,
            artifact_key_suffix="story",
            artifact_title="Story Content",
            artifact_icon="FileText"
        )
        
    except Exception as e:
        logger.error(f"Storywriter output failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"
        
        # Update result summary in plan
        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="storywriter",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step['id'],
            state=state,
            artifact_key_suffix="story",
            artifact_title="Story Content",
            is_error=True
        )
