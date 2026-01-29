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
from src.core.workflow.state import State

from .common import create_worker_response

logger = logging.getLogger(__name__)

async def storywriter_node(state: State) -> Command[Literal["visualizer"]]:
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
    
    # Provide context including artifacts
    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"
    
    # Build messages with prompt template
    messages = apply_prompt_template("storywriter", state)
    messages.append(HumanMessage(content=context, name="supervisor"))
    
    # Use bind_tools for streaming support + manual Pydantic validation
    llm = get_llm_by_type(AGENT_LLM_MAP["storywriter"])
    llm_with_tools = llm.bind_tools([StorywriterOutput])
    
    try:
        accumulated_args = ""
        final_tool_call = None
        
        # Stream the response
        async for chunk in llm_with_tools.astream(messages):
            if chunk.tool_call_chunks:
                for tool_call_chunk in chunk.tool_call_chunks:
                    # Append partial args
                    if tool_call_chunk.get("args"):
                        partial_args = tool_call_chunk["args"]
                        accumulated_args += partial_args
                        
                        # Dispatch raw partial JSON event
                        from langchain_core.callbacks.manager import adispatch_custom_event
                        await adispatch_custom_event(
                            "storywriter-partial-json",
                            {
                                "args": accumulated_args, # Send accumulated so far? Or delta? 
                                # sending accumulated is safer for "best-effort" parser if it expects full partial string
                                # But efficient delta is better if we just append?
                                # Let's send accumulated for simplicity with best-effort-json-parser 
                                # (it usually parses the whole string from scratch).
                                # To save bandwidth we could send delta, but let's stick to accumulated for robustness first.
                                "delta": partial_args 
                            },
                            config={"tags": ["storywriter_partial"]}
                        )
                    
                    if tool_call_chunk.get("name"):
                        # Capture tool name if needed (usually StorywriterOutput)
                        pass

        # At the end, parse the full accumulated JSON
        try:
            parsed_args = json.loads(accumulated_args)
            result = StorywriterOutput(**parsed_args)
        except json.JSONDecodeError:
            # Fallback/Retry logic could go here, but for now error out
             raise ValueError(f"Failed to parse final JSON from Storywriter: {accumulated_args[:100]}...")

        content_json = result.model_dump_json(exclude_none=True)
        result_summary = result.execution_summary
        logger.info(f"✅ Storywriter generated {len(result.slides)} slides (streaming)")
        
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
        logger.error(f"Storywriter streaming output failed: {e}")
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