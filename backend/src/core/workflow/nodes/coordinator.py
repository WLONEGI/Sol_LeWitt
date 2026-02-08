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
from src.core.workflow.nodes.orchestration import (
    _detect_intent,
    _detect_target_scope,
    _extract_latest_user_text,
    _hydrate_target_scope_from_ledger,
)

logger = logging.getLogger(__name__)
SUPPORTED_PRODUCT_TYPES = ("slide_infographic", "document_design", "comic")

class CoordinatorOutput(BaseModel):
    """Structured output for coordinator in a single LLM call."""
    product_type: Literal["slide_infographic", "document_design", "comic", "unsupported"] = Field(
        ...,
        description=(
            "Classified product category. "
            "Use slide_infographic/document_design/comic for supported requests; "
            "use unsupported for out-of-scope categories."
        ),
    )
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

async def coordinator_node(state: State, config: RunnableConfig) -> Command[Literal["plan_manager", "__end__"]]:
    """
    Coordinator Node: Unified scope + intent pre-processing and UX gatekeeper.
    Uses structured output to classify category and decide execution flow.
    """
    logger.info("Coordinator processing request (Unified Mode)")
    latest_user_text = _extract_latest_user_text(state)
    
    prompt_state = dict(state)
    prompt_state.setdefault("product_type", None)
    messages = apply_prompt_template("coordinator", prompt_state)
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
        "Coordinator Structured Response: product_type='%s', goto='%s', title='%s', response_len=%s",
        result.product_type,
        result.goto,
        result.title,
        len(result.response or "")
    )

    # 4. Decision Logic
    existing_product_type = state.get("product_type")
    if existing_product_type in SUPPORTED_PRODUCT_TYPES:
        if result.product_type != existing_product_type:
            logger.info(
                "Coordinator product_type overridden by lock: model=%s -> locked=%s",
                result.product_type,
                existing_product_type,
            )
        effective_product_type = existing_product_type
    else:
        effective_product_type = result.product_type

    goto_destination = "plan_manager" if result.goto == "planner" else "__end__"
    if effective_product_type == "unsupported" or effective_product_type not in SUPPORTED_PRODUCT_TYPES:
        goto_destination = "__end__"

    updates: dict = {
        "messages": [AIMessage(content=result.response)],
    }
    if effective_product_type in SUPPORTED_PRODUCT_TYPES:
        updates["product_type"] = effective_product_type
    if not state.get("request_intent"):
        updates["request_intent"] = _detect_intent(latest_user_text)
    if not state.get("target_scope"):
        detected_scope = _detect_target_scope(latest_user_text)
        if detected_scope:
            updates["target_scope"] = _hydrate_target_scope_from_ledger(
                detected_scope,
                state.get("asset_unit_ledger"),
            )

    if goto_destination == "plan_manager":
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
    return Command(
        update=updates,
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
