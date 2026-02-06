import logging
from typing import Literal

from langchain_core.messages import AIMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.infrastructure.llm.llm import get_llm_by_type
from src.shared.config import AGENT_LLM_MAP
from src.resources.prompts.template import apply_prompt_template
from src.core.workflow.state import State

logger = logging.getLogger(__name__)

class CoordinatorOutput(BaseModel):
    """Structured output for coordinator in a single LLM call."""
    response: str = Field(
        ...,
        description="User-facing response in Japanese. Must be polite and actionable."
    )
    goto: Literal["planner", "__end__"] = Field(
        ...,
        description="Next node. Use 'planner' when the request is production-ready; otherwise '__end__'."
    )
    title: str | None = Field(
        None,
        description="Short title (<=20 chars) only when goto is 'planner'. Use null otherwise."
    )

async def coordinator_node(state: State, config: RunnableConfig) -> Command[Literal["planner", "supervisor", "__end__"]]:
    """
    Coordinator Node: Gatekeeper & UX Manager (Unified).
    Uses structured output to decide execution flow while streaming JSON to the frontend.
    """
    logger.info("Coordinator processing request (Unified Mode)")
    
    messages = apply_prompt_template("coordinator", state)
    logger.debug(f"Coordinator Messages: {messages}")
    
    # 1. Setup LLM with structured output
    llm = get_llm_by_type(AGENT_LLM_MAP["coordinator"], streaming=True)
    structured_llm = llm.with_structured_output(CoordinatorOutput)
    
    # 2. Add run_name for better visibility
    stream_config = config.copy()
    stream_config["run_name"] = "coordinator" # Unified run name
    
    # 3. Stream Integration
    # We stream JSON chunks to the frontend (buffered on BFF), and parse the final structured output here.
    # Using `ainvoke` with streaming=True allows the underlying callbacks to fire for tokens.
    
    logger.info("Coordinator: Invoking model (structured output)...")
    result: CoordinatorOutput = await structured_llm.ainvoke(messages, config=stream_config)

    logger.debug(
        "Coordinator Structured Response: goto='%s', title='%s', response_len=%s",
        result.goto,
        result.title,
        len(result.response or "")
    )

    # 4. Decision Logic
    goto_destination = "planner" if result.goto == "planner" else "__end__"

    if goto_destination == "planner":
        thread_id = config.get("configurable", {}).get("thread_id")
        user_uid = config.get("configurable", {}).get("user_uid")
        title = result.title or _derive_fallback_title(state)  # CHANGED: deterministic fallback
        saved_title = await _save_title(thread_id, user_uid, title)
        if saved_title:
            await adispatch_custom_event(
                "title_generated",
                {"title": saved_title},
                config=config
            )
    
    # 5. Return Command
    # We return the message so it's added to history.
    return Command(
        update={"messages": [AIMessage(content=result.response)]},
        goto=goto_destination
    )

def _derive_fallback_title(state: State) -> str:
    """Derive a short deterministic title from recent user input."""
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human" and isinstance(msg.content, str) and msg.content.strip():
            return msg.content.strip()[:20]
    return "プレゼン資料"

async def _save_title(
    thread_id: str | None,
    owner_uid: str | None,
    title: str | None,
) -> str | None:
    """Saves a title to DB if not already present. Returns the saved or existing title."""
    try:
        # Import internally to avoid circular dependency with service -> build_graph -> coordinator
        from src.core.workflow.service import _manager
        
        if not thread_id or not title or not owner_uid:
            return None

        # Check if pool is available
        if not _manager.pool:
            logger.warning("DB Pool not initialized, skipping title generation.")
            return None

        # 0. Check if title already exists (Idempotency) - Reuse pool
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT title FROM threads WHERE thread_id = %s AND owner_uid = %s",
                    (thread_id, owner_uid),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    logger.info(f"Title already exists for thread {thread_id}, skipping generation.")
                    return row[0]

        # 1. Save to DB - Reuse pool
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO threads (thread_id, owner_uid, title, summary) 
                    VALUES (%s, %s, %s, %s) 
                    ON CONFLICT (thread_id) 
                    DO UPDATE SET title = EXCLUDED.title, updated_at = NOW()
                    WHERE threads.owner_uid = EXCLUDED.owner_uid;
                    """,
                    (thread_id, owner_uid, title, "")
                )
                if cur.rowcount == 0:
                    logger.warning(
                        "Skip title update due to owner mismatch. thread_id=%s owner_uid=%s",
                        thread_id,
                        owner_uid,
                    )
                    return None
                await conn.commit()
        
        logger.info(f"Title saved: {title}")
        return title
        
    except Exception as e:
        logger.warning(f"Failed to save session title: {e}")
        return None
