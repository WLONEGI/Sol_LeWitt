import logging
from typing import Literal

from langchain_core.messages import HumanMessage, AIMessage
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks.manager import adispatch_custom_event
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
    messages = apply_prompt_template("coordinator", state)
    logger.debug(f"Coordinator Messages: {messages}")
    
    # 1. Decision Step (Blocking but fast)
    llm = get_llm_by_type(AGENT_LLM_MAP["coordinator"])
    structured_llm = llm.with_structured_output(CoordinatorDecision)
    
    try:
        # We don't propagate config here to avoid streaming the partial JSON of the decision
        # We want this to complete fast and silently.
        # Actually, if we pass config, it sends events. If the frontend can handle "intermediate" events, it's fine.
        # But typically we hide the decision process.
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
        

        
        # Generate a polite handoff message (Streamed)
        # We add a hint to the model to generate the confirmation
        handoff_prompt = messages + [
            HumanMessage(content=f"Decision: Handoff to Planner.\nReasoning: {decision_output.reasoning}\n\nTask: Generate a polite, encouraging, Japanese confirmation message to the user stating that we are starting the planning process based on the request. Do NOT describe technical details like 'nodes'.")
        ]
        
        response = await llm.ainvoke(handoff_prompt, config=config)
        
        return Command(
            update={"messages": [response]},
            goto="planner",
        )
    
    else: # reply_to_user
        logger.info("[DEBUG] Replying to user branch entered. Starting LLM stream.")
        # Just generate the natural response (Streamed)
        # Use astream to ensure token-level events are emitted for astream_events v2
        response_content = ""
        try:
            async for chunk in llm.astream(messages, config=config):
                content = chunk.content
                response_content += content
                await adispatch_custom_event("message_delta", content, config=config)
        except Exception as stream_e:
            logger.error(f"[DEBUG] Error during Coordinator streaming: {stream_e}", exc_info=True)
            raise stream_e

        if not response_content:
            logger.warning("[DEBUG] Coordinator generated empty response. Using fallback.")
            response_content = "申し訳ありません、応答を生成できませんでした。"
            await adispatch_custom_event("message_delta", response_content, config=config)

        logger.info(f"[DEBUG] Coordinator streaming complete. Total content length: {len(response_content)}")
            
        return Command(
            update={"messages": [AIMessage(content=response_content, name="coordinator")]},
            goto="__end__"
        )

async def _generate_and_save_title(state: State, thread_id: str):
    """Generates a title using Flash model and saves to DB."""
    try:
        from src.shared.config.settings import settings
        import psycopg
        
        if not thread_id: return

        conn_str = settings.connection_string
        if not conn_str: return

        # 0. Check if title already exists (Idempotency)
        async with await psycopg.AsyncConnection.connect(conn_str, autocommit=True) as ac:
            async with ac.cursor() as cur:
                await cur.execute("SELECT title FROM threads WHERE thread_id = %s", (thread_id,))
                row = await cur.fetchone()
                if row and row[0]:
                    logger.info(f"Title already exists for thread {thread_id}, skipping generation.")
                    return

        # 1. Generate Title
        # Use a lightweight model for this metadata task
        # Use user-configured BASIC_MODEL or fallback
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
        
        # 2. Save to DB (Reconnect or reuse connection? Reconnecting for simplicity/safety in async context)
        async with await psycopg.AsyncConnection.connect(conn_str, autocommit=True) as ac:
            async with ac.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO threads (thread_id, title, summary) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (thread_id) 
                    DO UPDATE SET title = EXCLUDED.title, updated_at = NOW();
                    """,
                    (thread_id, title, "")
                )
        
        # 3. Emit Event
        await adispatch_custom_event("title_generated", {"title": title, "thread_id": thread_id})
        logger.info(f"Title generated and saved: {title}")
        
    except Exception as e:
        logger.warning(f"Failed to generate session title: {e}")

