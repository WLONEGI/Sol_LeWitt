import logging
from typing import Literal

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.infrastructure.llm.llm import get_llm_by_type
from src.shared.config import AGENT_LLM_MAP
from src.resources.prompts.template import apply_prompt_template
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

class HandoffToPlanner(BaseModel):
    """
    Call this tool when the user's request is ready for production (topic is clear).
    This will trigger the handoff to the planning team.
    """
    reasoning: str = Field(
        ...,
        description="Reasoning for why the request is ready for production (e.g., 'Topic is clear', 'User confirmed intent')."
    )

async def coordinator_node(state: State, config: RunnableConfig) -> Command[Literal["planner", "supervisor", "__end__"]]:
    """
    Coordinator Node: Gatekeeper & UX Manager (Unified).
    Uses tool calling to decide execution flow while simultaneously streaming the response to the user.
    """
    logger.info("Coordinator processing request (Unified Mode)")
    
    messages = apply_prompt_template("coordinator", state)
    logger.debug(f"Coordinator Messages: {messages}")
    
    # 1. Setup LLM with Tool
    # We bind the HandoffToPlanner tool. 
    # The model is instructed (via prompt) to call this tool if appropriate, 
    # AND to generate a polite text response in the same turn.
    llm = get_llm_by_type(AGENT_LLM_MAP["coordinator"], streaming=True)
    llm_with_tools = llm.bind_tools([HandoffToPlanner])
    
    # 2. Add run_name for better visibility
    stream_config = config.copy()
    stream_config["run_name"] = "coordinator" # Unified run name
    
    # 3. Stream Integration
    # We want to stream the text chunks to the frontend as they arrive (handled by callbacks), 
    # while capturing the final output to utilize any tool calls.
    # Using `ainvoke` with streaming=True allows the underlying callbacks to fire for tokens,
    # and returns the final AIMessage with tool_calls.
    
    logger.info("Coordinator: Invoking model (streaming events should flow to frontend)...")
    response_message = await llm_with_tools.ainvoke(messages, config=stream_config)
    
    logger.debug(f"Coordinator Response: content='{response_message.content}', tool_calls={response_message.tool_calls}")
    
    # 4. Decision Logic
    goto_destination = "__end__"
    
    if response_message.tool_calls:
        # Check if the desired tool was called
        for tc in response_message.tool_calls:
            if tc["name"] == "HandoffToPlanner":
                logger.info(f"Handoff tool called. Reasoning: {tc['args'].get('reasoning')}")
                goto_destination = "planner"
                
                # Async Title Generation (Preserved logic)
                thread_id = config.get("configurable", {}).get("thread_id")
                # We await this to ensure title is ready before next steps if needed
                title = await _generate_and_save_title(state, thread_id)
                if title:
                    await adispatch_custom_event(
                        "title_generated",
                        {"title": title},
                        config=config
                    )
                break
    
    # 5. Return Command
    # We return the message so it's added to history.
    return Command(
        update={"messages": [response_message]},
        goto=goto_destination
    )

async def _generate_and_save_title(state: State, thread_id: str) -> str | None:
    """Generates a title using Flash model and saves to DB. Returns the title if generated/found."""
    try:
        from src.shared.config.settings import settings
        # Import internally to avoid circular dependency with service -> build_graph -> coordinator
        from src.core.workflow.service import _manager
        
        if not thread_id: return

        # Check if pool is available
        if not _manager.pool:
            logger.warning("DB Pool not initialized, skipping title generation.")
            return

        # 0. Check if title already exists (Idempotency) - Reuse pool
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT title FROM threads WHERE thread_id = %s", (thread_id,))
                row = await cur.fetchone()
                if row and row[0]:
                    logger.info(f"Title already exists for thread {thread_id}, skipping generation.")
                    return row[0]

        # 1. Generate Title
        model_name = settings.BASIC_MODEL or "gemini-1.5-flash"
        llm = get_llm_by_type(model_name) 
        
        messages = state.get("messages", [])
        if not messages: return None

        # Simple context extraction
        context = "\n".join([f"{m.type}: {m.content}" for m in messages if isinstance(m.content, str)])
        
        prompt = f"""
        以下の会話の文脈に基づいて、スライド生成タスクの短いタイトル（20文字以内）を生成してください。
        タイトルのみを出力してください。鉤括弧や装飾は不要です。
        
        Conversation:
        {context}
        """
        
        response = await llm.ainvoke(prompt)
        title = response.content.strip()
        
        # 2. Save to DB - Reuse pool
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO threads (thread_id, title, summary) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (thread_id) 
                    DO UPDATE SET title = EXCLUDED.title, updated_at = NOW();
                    """,
                    (thread_id, title, "")
                )
        
        logger.info(f"Title generated and saved: {title}")
        return title
        
    except Exception as e:
        logger.warning(f"Failed to generate session title: {e}")
        return None

