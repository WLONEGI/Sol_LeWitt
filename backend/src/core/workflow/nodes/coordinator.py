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

class CoordinatorDecision(BaseModel):
    """Decision made by the Coordinator."""
    decision: Literal["handoff_to_planner", "reply_to_user"] = Field(
        ...,
        description="Whether to handoff the task to the planner (production request) or reply to the user (clarification/chat)."
    )
    reasoning: str = Field(
        ...,
        description="Brief reasoning for the decision."
    )

async def coordinator_node(state: State, config: RunnableConfig) -> Command[Literal["planner", "supervisor", "__end__"]]:
    """
    Coordinator Node: Gatekeeper & UX Manager (HITL).
    Decides execution flow first, then streams response if needed.
    """
    logger.info("Coordinator processing request")
    
    messages = apply_prompt_template("coordinator", state)
    logger.debug(f"Coordinator Messages: {messages}")
    
    # 1. Decision Step (Call-time binding)
    llm = get_llm_by_type(AGENT_LLM_MAP["coordinator"])
    
    try:
        # Use with_structured_output explicitly since gemini-3/2.0-flash with current lib 
        # doesn't reliably parse response_format in ainvoke.
        structured_llm = llm.with_structured_output(CoordinatorDecision)
        decision_output: CoordinatorDecision = await structured_llm.ainvoke(messages)
        logger.debug(f"[DEBUG] Coordinator decision response: {decision_output.decision} (Reasoning: {decision_output.reasoning})")
    except Exception as e:
        logger.error(f"[DEBUG] Structured output parsing failed IN COORDINATOR: {e}", exc_info=True)
        return Command(
            update={"messages": [AIMessage(content="申し訳ありません、判断中にエラーが発生しました。", name="coordinator")]},
            goto="__end__"
        )

    # 2. Execution Step (Streaming)
    if decision_output.decision == "handoff_to_planner":
        logger.info("Handing off to planner.")
        
        # Async Title Generation
        thread_id = config.get("configurable", {}).get("thread_id")
        await _generate_and_save_title(state, thread_id)
        
        # Generate a polite handoff message (Standard Streaming)
        handoff_prompt = messages + [
            HumanMessage(content=f"Decision: Handoff to Planner.\nReasoning: {decision_output.reasoning}\n\nTask: Generate a polite, encouraging, Japanese confirmation message to the user stating that we are starting the planning process based on the request. Do NOT describe technical details like 'nodes'.")
        ]
        
        # We use astream to ensure individual tokens are emitted as on_chat_model_stream.
        response_content = ""
        async for chunk in llm.astream(handoff_prompt, config=config):
            if chunk.content:
                if isinstance(chunk.content, str):
                    response_content += chunk.content
                elif isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and "text" in part:
                            response_content += part["text"]
                        elif isinstance(part, str):
                            response_content += part
        
        return Command(
            update={"messages": [AIMessage(content=response_content, name="coordinator")]},
            goto="planner",
        )
    
    else: # reply_to_user
        logger.info("Replying to user branch entered. Using standard streaming.")
        # Just generate the natural response (Standard Streaming)
        response_content = ""
        async for chunk in llm.astream(messages, config=config):
            if chunk.content:
                if isinstance(chunk.content, str):
                    response_content += chunk.content
                elif isinstance(chunk.content, list):
                    for part in chunk.content:
                        if isinstance(part, dict) and "text" in part:
                            response_content += part["text"]
                        elif isinstance(part, str):
                            response_content += part

        if not response_content:
            logger.warning("Coordinator generated empty response. Using fallback.")
            response_content = "申し訳ありません、応答を生成できませんでした。"

        return Command(
            update={"messages": [AIMessage(content=response_content, name="coordinator")]},
            goto="__end__"
        )

async def _generate_and_save_title(state: State, thread_id: str):
    """Generates a title using Flash model and saves to DB."""
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
                    return

        # 1. Generate Title
        model_name = settings.BASIC_MODEL or "gemini-1.5-flash"
        llm = get_llm_by_type(model_name) 
        
        messages = state.get("messages", [])
        if not messages: return

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
        
    except Exception as e:
        logger.warning(f"Failed to generate session title: {e}")

