"""
FastAPI application for Spell - LangServe Edition.
Uses langserve add_routes for standard LangGraph API exposure.
"""

import json
import os
import logging
import asyncio
import re
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse

from langserve import add_routes
from langserve.serialization import WellKnownLCSerializer
import langserve.serialization
from langgraph.types import Send

from src.core.workflow.service import initialize_graph, close_graph, _manager
from src.infrastructure.auth.firebase import verify_firebase_token
from src.infrastructure.auth.user_store import upsert_user
from src.domain.designer.generator import generate_image
from src.infrastructure.storage.gcs import upload_to_gcs, download_blob_as_bytes

# Configure logging
logger = logging.getLogger(__name__)


# === Monkey Patch for Send Objects ===

def _patch_langserve_serialization():
    """
    Monkey patch LangServe's serializer to handle LangGraph's internal `Send` objects.
    These objects are returned by conditional edges and should not be sent to the client.
    We return None to filter them out.
    """
    import langserve.serialization
    original_default = langserve.serialization.default
    
    def patched_default(obj: Any) -> Any:
        if isinstance(obj, Send):
            return None
        return original_default(obj)

    langserve.serialization.default = patched_default

_patch_langserve_serialization()

DEFAULT_RECURSION_LIMIT = 50
_THREADS_TABLE_READY = False
_THREADS_TABLE_LOCK = asyncio.Lock()

# === LangServe Input/Output Schemas ===

class ChatInput(BaseModel):
    """Inner input schema for the graph state.
    This corresponds to the fields in the State TypedDict.
    """
    messages: list[Any] = Field(..., description="List of input messages")

class ChatRequest(BaseModel):
    """Wrapped request schema matching LangServe format:
    {
        "input": { "messages": [...] },
        "config": { "configurable": { ... } }
    }
    """
    input: ChatInput = Field(..., description="State input")
    config: Optional[dict[str, Any]] = Field(default=None, description="Configuration dictionary")


class ChatOutput(BaseModel):
    """Output schema for LangServe - LangGraph returns full state."""
    messages: list[Any] = Field(default_factory=list)
    plan: list[Any] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)


def _extract_uid(decoded: dict[str, Any]) -> str:
    uid = decoded.get("uid") or decoded.get("user_id") or decoded.get("sub")
    if not uid:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return str(uid)


async def _authenticate_request(request: Request) -> tuple[dict[str, Any], str]:
    auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth_header or not auth_header.lower().startswith("bearer "):
        logger.warning("Auth failed: missing Authorization bearer token.")
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")

    id_token = auth_header.split(" ", 1)[1].strip()
    if not id_token:
        logger.warning("Auth failed: empty bearer token.")
        raise HTTPException(status_code=401, detail="Missing Authorization bearer token")

    try:
        decoded = verify_firebase_token(id_token)
    except Exception as e:
        logger.warning(f"Auth failed: invalid or expired token. {e}")
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    uid = _extract_uid(decoded)

    try:
        await upsert_user(_manager.pool, decoded)
    except Exception as e:
        logger.error(f"Failed to upsert user: {e}")
        raise HTTPException(status_code=500, detail="Failed to persist user")

    request.state.user_uid = uid
    request.state.user_decoded = decoded
    return decoded, uid


async def _ensure_threads_table(pool) -> None:
    global _THREADS_TABLE_READY
    if _THREADS_TABLE_READY:
        return

    async with _THREADS_TABLE_LOCK:
        if _THREADS_TABLE_READY:
            return

        async with pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS threads (
                        thread_id TEXT PRIMARY KEY,
                        owner_uid TEXT,
                        title TEXT,
                        summary TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await cur.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS owner_uid TEXT;")
                await cur.execute(
                    """
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1
                            FROM pg_constraint
                            WHERE conname = 'threads_owner_uid_fkey'
                        ) THEN
                            ALTER TABLE threads
                            ADD CONSTRAINT threads_owner_uid_fkey
                            FOREIGN KEY (owner_uid) REFERENCES users(uid) ON DELETE CASCADE;
                        END IF;
                    END $$;
                    """
                )
                await cur.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_threads_owner_updated_at
                    ON threads(owner_uid, updated_at DESC);
                    """
                )
                await conn.commit()
        _THREADS_TABLE_READY = True


def _build_graph_config(thread_id: str, uid: str) -> dict[str, Any]:
    return {
        "configurable": {
            "thread_id": thread_id,
            "checkpoint_ns": uid,
            "user_uid": uid,
        }
    }


async def _ensure_thread_access(
    pool,
    *,
    thread_id: str,
    uid: str,
    create_if_missing: bool,
) -> None:
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    if not pool:
        raise HTTPException(status_code=503, detail="Database not initialized")

    await _ensure_threads_table(pool)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT owner_uid FROM threads WHERE thread_id = %s",
                (thread_id,),
            )
            row = await cur.fetchone()
            if row:
                owner_uid = row[0]
                if owner_uid and owner_uid != uid:
                    raise HTTPException(status_code=404, detail="Thread not found")
                if not owner_uid:
                    raise HTTPException(
                        status_code=409,
                        detail="Thread ownership is not initialized for this thread",
                    )
                if create_if_missing:
                    await cur.execute(
                        "UPDATE threads SET updated_at = NOW() WHERE thread_id = %s",
                        (thread_id,),
                    )
                    await conn.commit()
                return

            if not create_if_missing:
                raise HTTPException(status_code=404, detail="Thread not found")

            await cur.execute(
                """
                INSERT INTO threads (thread_id, owner_uid, title, summary, created_at, updated_at)
                VALUES (%s, %s, NULL, '', NOW(), NOW())
                ON CONFLICT (thread_id) DO NOTHING;
                """,
                (thread_id, uid),
            )
            if cur.rowcount == 0:
                await cur.execute(
                    "SELECT owner_uid FROM threads WHERE thread_id = %s",
                    (thread_id,),
                )
                conflict_row = await cur.fetchone()
                conflict_owner = conflict_row[0] if conflict_row else None
                if conflict_owner != uid:
                    raise HTTPException(status_code=404, detail="Thread not found")
            await conn.commit()


# === Application Lifecycle ===

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events.
    """
    logger.info("🚀 Starting Spell API (LangServe Edition)...")
    logger.info("Initializing application resources...")
    try:
        await initialize_graph()
        
        # Add LangServe routes after graph initialization
        graph = _manager.get_graph()
        graph_with_types = graph.with_types(input_type=ChatInput, output_type=ChatOutput)
        
        # Modifier to inject thread_id from headers (bypassing strict body schema)
        def per_req_config_modifier(config: dict, request: Request) -> dict:
            thread_id = request.headers.get("X-Thread-Id")
            if thread_id:
                config.setdefault("configurable", {})["thread_id"] = thread_id
            uid = getattr(request.state, "user_uid", None)
            if uid:
                config.setdefault("configurable", {})["checkpoint_ns"] = uid
                config.setdefault("configurable", {})["user_uid"] = uid
            config.setdefault("recursion_limit", DEFAULT_RECURSION_LIMIT)
            return config

        add_routes(
            app,
            graph_with_types,
            path="/api/chat",
            enabled_endpoints=["invoke", "batch", "stream", "stream_log"], # Explicitly exclude stream_events to use custom handler
            per_req_config_modifier=per_req_config_modifier,
            # serializer argument removed; using patched WellKnownLCSerializer default
        )
        logger.info("✅ LangServe routes added at /api/chat/*")
        
        logger.info("✅ Application initialized successfully.")
        
    except Exception as e:
        logger.critical(f"❌ Application startup failed: {e}")
        raise e
    yield
    logger.info("Cleaning up application resources...")
    await close_graph()
    logger.info("👋 Application shutdown complete.")


# === Create FastAPI App ===

app = FastAPI(
    title="Spell API",
    description="API for Spell LangGraph-based agent workflow (LangServe Edition)",
    version="0.2.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _is_protected_path(path: str) -> bool:
    if path.startswith("/api/chat"):
        return True
    if path == "/api/history":
        return True
    if path.startswith("/api/threads/"):
        return True
    return False


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    if not _is_protected_path(request.url.path):
        return await call_next(request)

    try:
        await _authenticate_request(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    except Exception as exc:
        logger.exception(f"Auth middleware failed: {exc}")
        return JSONResponse(status_code=500, content={"detail": "Authentication failed"})

    return await call_next(request)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation Error: {exc.errors()}")
    try:
        body = await request.body()
        logger.error(f"Body: {body.decode('utf-8')}")
    except Exception:
        pass
    return JSONResponse(
        status_code=422,
        content={"detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler to ensure all errors return JSON.
    """
    logger.exception(f"Unhandled Global Exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


# === Custom Stream Events Endpoint ===

@app.post("/api/chat/stream_events")
async def custom_stream_events(request: Request, input_data: ChatRequest):
    """
    Custom implementation of stream_events to filter data sent to BFF.
    Only sends:
    - on_chat_model_stream (without citation_metadata)
    - on_custom_event (excluding citation_metadata)
    """
    try:
        uid = getattr(request.state, "user_uid", None)
        if not isinstance(uid, str) or not uid:
            raise HTTPException(status_code=401, detail="Unauthorized")

        # Re-fetch graph with types to ensure it's available
        graph = _manager.get_graph()
        if not graph:
            raise HTTPException(status_code=503, detail="Graph not initialized")
            
        graph_with_types = graph.with_types(input_type=ChatInput, output_type=ChatOutput)

        # 1. Prepare Config (Thread ID)
        thread_id = request.headers.get("X-Thread-Id")
        if not thread_id:
            raise HTTPException(status_code=400, detail="Missing X-Thread-Id header")

        await _ensure_thread_access(
            _manager.pool,
            thread_id=thread_id,
            uid=uid,
            create_if_missing=True,
        )
        
        # 2. Define Generator
        async def event_generator():
            try:
                # Use the 'input' field from the payload for the graph input
                # pydantic model 'input' field will contain ChatInput instance
                graph_input = input_data.input.model_dump()
                
                # Merge request-level config (Thread ID) with payload config
                merged_config = input_data.config or {}
                merged_config.setdefault("configurable", {})
                merged_config["configurable"]["thread_id"] = thread_id
                merged_config["configurable"]["checkpoint_ns"] = uid
                merged_config["configurable"]["user_uid"] = uid
                merged_config.setdefault("recursion_limit", DEFAULT_RECURSION_LIMIT)
                
                # Stream events from the graph
                async for event in graph_with_types.astream_events(
                    graph_input,
                    merged_config,
                    version="v2"
                ):
                    event_type = event.get("event")
                    event_run_name = event.get("metadata", {}).get("run_name")
                    
                    # Filter Logic
                    if event_type == "on_chat_model_stream":
                        # Pass through chat model tokens
                        yield f"data: {json.dumps(event, default=langserve.serialization.default)}\n\n"
                        
                    elif event_type == "on_custom_event":
                        event_name = event.get("name")
                        
                        # Exclude citation_metadata standalone event
                        if event_name == "citation_metadata":
                            continue
                            
                        # Pass through other custom events (e.g. research_worker_token)
                        yield f"data: {json.dumps(event, default=langserve.serialization.default)}\n\n"
                        
                    # All other events (on_chain_start, on_tool_start, etc.) are IGNORED
            except Exception as stream_err:
                logger.error(f"Error inside stream generator: {stream_err}")
                yield f"data: {json.dumps({'event': 'error', 'data': str(stream_err)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in custom stream setup: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === Health Check ===

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}


# === History Endpoints ===

_STEP_ARTIFACT_KEY_PATTERN = re.compile(r"^step_(\d+)_(\w+)$")


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def _normalize_plan(plan: Any) -> list[dict[str, Any]]:
    if not isinstance(plan, list):
        return []

    normalized: list[dict[str, Any]] = []
    for index, step in enumerate(plan):
        if not isinstance(step, dict):
            continue
        row = dict(step)
        status = row.get("status")
        if status == "complete":
            status = "completed"
        elif status == "todo":
            status = "pending"
        elif status not in ("pending", "in_progress", "completed"):
            status = "pending"
        row["status"] = status
        row.setdefault("id", index + 1)
        normalized.append(jsonable_encoder(row))
    return normalized


def _extract_step_artifact_meta(artifact_id: str) -> tuple[int, str]:
    match = _STEP_ARTIFACT_KEY_PATTERN.match(artifact_id)
    if not match:
        return (10**9, artifact_id)
    return (int(match.group(1)), match.group(2))


def _serialize_message(msg: Any) -> dict[str, Any] | None:
    msg_type = getattr(msg, "type", None)
    if msg_type == "tool":
        return None

    role = "assistant"
    if msg_type == "human":
        role = "user"
    elif msg_type == "system":
        role = "system"

    content = getattr(msg, "content", "")
    parts: list[dict[str, Any]] = []
    text_chunks: list[str] = []

    def append_text(text: str) -> None:
        if not text:
            return
        parts.append({"type": "text", "text": text})
        text_chunks.append(text)

    def append_reasoning(text: str) -> None:
        if not text:
            return
        parts.append({"type": "reasoning", "text": text})

    if isinstance(content, str):
        append_text(content)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict):
                part_type = part.get("type")
                part_text = part.get("text")
                if not isinstance(part_text, str):
                    continue
                if part_type in ("thinking", "reasoning"):
                    append_reasoning(part_text)
                else:
                    append_text(part_text)
            elif isinstance(part, str):
                append_text(part)
    elif isinstance(content, dict):
        part_type = content.get("type")
        part_text = content.get("text")
        if isinstance(part_text, str):
            if part_type in ("thinking", "reasoning"):
                append_reasoning(part_text)
            else:
                append_text(part_text)

    additional_kwargs = getattr(msg, "additional_kwargs", {}) or {}
    reasoning = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        if not any(part.get("type") == "reasoning" for part in parts):
            parts.insert(0, {"type": "reasoning", "text": reasoning})

    if additional_kwargs.get("ui_type") == "plan_update":
        plan_data = additional_kwargs.get("plan")
        if isinstance(plan_data, list):
            parts.append({
                "type": "data-plan_update",
                "data": {
                    "plan": plan_data,
                    "title": additional_kwargs.get("title"),
                    "description": additional_kwargs.get("description"),
                    "ui_type": "plan_update",
                }
            })

    return {
        "role": role,
        "content": "".join(text_chunks),
        "parts": parts,
        "name": getattr(msg, "name", None),
        "id": getattr(msg, "id", None),
        "metadata": jsonable_encoder(additional_kwargs),
        "sources": additional_kwargs.get("sources", []),
    }


def _serialize_messages(messages: Any) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    serialized: list[dict[str, Any]] = []
    for msg in messages:
        item = _serialize_message(msg)
        if item is not None:
            serialized.append(item)
    return serialized


def _build_story_outline(slides: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for slide in slides:
        number = slide.get("slide_number", "?")
        title = slide.get("title", "")
        lines.append(f"## Slide {number}: {title}")
        bullet_points = slide.get("bullet_points")
        if isinstance(bullet_points, list):
            for point in bullet_points:
                if isinstance(point, str):
                    lines.append(f"- {point}")
        description = slide.get("description")
        if isinstance(description, str) and description.strip():
            lines.append(description)
        lines.append("")
    return "\n".join(lines).strip()


def _build_visual_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []

    prompts = data.get("prompts")
    if not isinstance(prompts, list):
        return None, []

    events: list[dict[str, Any]] = []
    slides: list[dict[str, Any]] = []

    for prompt in sorted(prompts, key=lambda item: item.get("slide_number", 0) if isinstance(item, dict) else 0):
        if not isinstance(prompt, dict):
            continue
        slide_number = prompt.get("slide_number")
        if not isinstance(slide_number, int):
            continue

        structured_prompt = prompt.get("structured_prompt")
        structured_title = (
            structured_prompt.get("main_title")
            if isinstance(structured_prompt, dict)
            else None
        )
        title = prompt.get("title") or structured_title or f"Slide {slide_number}"
        image_url = prompt.get("generated_image_url")
        prompt_text = prompt.get("compiled_prompt") or prompt.get("image_generation_prompt")
        status = "completed" if isinstance(image_url, str) and image_url else "streaming"

        slide: dict[str, Any] = {
            "slide_number": slide_number,
            "title": title,
            "status": status,
        }
        if isinstance(image_url, str) and image_url:
            slide["image_url"] = image_url
        if isinstance(prompt_text, str) and prompt_text:
            slide["prompt_text"] = prompt_text
        if structured_prompt is not None:
            slide["structured_prompt"] = structured_prompt
        if prompt.get("rationale") is not None:
            slide["rationale"] = prompt.get("rationale")
        if prompt.get("layout_type") is not None:
            slide["layout_type"] = prompt.get("layout_type")
        if prompt.get("selected_inputs") is not None:
            slide["selected_inputs"] = prompt.get("selected_inputs")
        slides.append(slide)

        events.append({
            "type": "data-visual-image",
            "data": {
                "artifact_id": artifact_id,
                "deck_title": "Generated Slides",
                "slide_number": slide_number,
                "title": title,
                "image_url": image_url,
                "prompt_text": prompt_text,
                "structured_prompt": structured_prompt,
                "rationale": prompt.get("rationale"),
                "layout_type": prompt.get("layout_type"),
                "selected_inputs": prompt.get("selected_inputs"),
                "status": status,
            }
        })

    pdf_url = data.get("combined_pdf_url")
    if isinstance(pdf_url, str) and pdf_url:
        events.append({
            "type": "data-visual-pdf",
            "data": {
                "artifact_id": artifact_id,
                "deck_title": "Generated Slides",
                "pdf_url": pdf_url,
                "status": "completed",
            }
        })

    if not slides:
        return None, events

    is_completed = all(bool(slide.get("image_url")) for slide in slides)
    artifact = {
        "id": artifact_id,
        "type": "slide_deck",
        "title": "Generated Slides",
        "content": {
            "slides": slides,
            "pdf_url": pdf_url,
        },
        "version": 1,
        "status": "completed" if is_completed else "streaming",
    }
    return artifact, events


def _build_story_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []
    slides = data.get("slides")
    if not isinstance(slides, list):
        return None, []

    normalized_slides = [jsonable_encoder(slide) for slide in slides if isinstance(slide, dict)]
    event = {
        "type": "data-outline",
        "data": {
            "artifact_id": artifact_id,
            "slides": normalized_slides,
            "title": "Slide Outline",
        }
    }

    artifact = {
        "id": artifact_id,
        "type": "outline",
        "title": "Slide Outline",
        "content": _build_story_outline(normalized_slides),
        "version": 1,
        "status": "completed",
    }
    return artifact, [event]


def _build_data_analyst_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []

    if "analysis_report" not in data and "execution_summary" not in data:
        return None, []

    summary = str(data.get("execution_summary") or "")
    lowered_summary = summary.lower()
    is_failed = "error" in lowered_summary or "失敗" in summary or "エラー" in summary
    status = "failed" if is_failed else "completed"

    artifact = {
        "id": artifact_id,
        "type": "data_analyst",
        "title": "Data Analyst",
        "content": {
            "output": jsonable_encoder(data),
        },
        "version": 1,
        "status": status,
    }

    events = [
        {
            "type": "data-analyst-start",
            "data": {
                "artifact_id": artifact_id,
                "title": "Data Analyst",
            }
        },
        {
            "type": "data-analyst-output",
            "data": {
                "artifact_id": artifact_id,
                "title": "Data Analyst",
                "output": jsonable_encoder(data),
                "status": status,
            }
        },
        {
            "type": "data-analyst-complete",
            "data": {
                "artifact_id": artifact_id,
                "status": status,
            }
        }
    ]
    return artifact, events


def _build_fallback_artifact(artifact_id: str, value: Any) -> dict[str, Any]:
    parsed = _safe_json_loads(value)
    if isinstance(parsed, (dict, list)):
        content = json.dumps(parsed, ensure_ascii=False, indent=2)
    else:
        content = str(parsed)
    return {
        "id": artifact_id,
        "type": "report",
        "title": artifact_id,
        "content": content,
        "version": 1,
        "status": "completed",
    }


def _build_snapshot_payload(thread_id: str, state_values: dict[str, Any]) -> dict[str, Any]:
    messages = _serialize_messages(state_values.get("messages", []))
    plan = _normalize_plan(state_values.get("plan", []))
    raw_artifacts = state_values.get("artifacts") or {}
    ui_events: list[dict[str, Any]] = []
    artifacts: dict[str, Any] = {}

    if plan:
        ui_events.append({
            "type": "data-plan_update",
            "data": {
                "plan": plan,
                "ui_type": "plan_update",
                "title": "Execution Plan",
                "description": "The updated execution plan.",
            }
        })

    if isinstance(raw_artifacts, dict):
        ordered_artifact_ids = sorted(raw_artifacts.keys(), key=_extract_step_artifact_meta)
        for artifact_id in ordered_artifact_ids:
            value = raw_artifacts.get(artifact_id)
            if value is None:
                continue

            _, suffix = _extract_step_artifact_meta(artifact_id)
            artifact: dict[str, Any] | None = None
            events: list[dict[str, Any]] = []

            if suffix == "visual":
                artifact, events = _build_visual_artifact(artifact_id, value)
            elif suffix == "story":
                artifact, events = _build_story_artifact(artifact_id, value)
            elif suffix == "data":
                artifact, events = _build_data_analyst_artifact(artifact_id, value)
            else:
                parsed = _safe_json_loads(value)
                if isinstance(parsed, dict) and "prompts" in parsed:
                    artifact, events = _build_visual_artifact(artifact_id, parsed)
                elif isinstance(parsed, dict) and "slides" in parsed:
                    artifact, events = _build_story_artifact(artifact_id, parsed)
                elif isinstance(parsed, dict) and (
                    "analysis_report" in parsed or "execution_summary" in parsed
                ):
                    artifact, events = _build_data_analyst_artifact(artifact_id, parsed)

            if artifact is None:
                artifact = _build_fallback_artifact(artifact_id, value)

            artifacts[artifact_id] = jsonable_encoder(artifact)
            if events:
                ui_events.extend(events)

    return {
        "thread_id": thread_id,
        "messages": messages,
        "plan": plan,
        "artifacts": artifacts,
        "ui_events": ui_events,
    }

@app.get("/api/history")
async def get_history(request: Request):
    """
    Get conversation history from the threads table.
    """
    try:
        uid = getattr(request.state, "user_uid", None)
        if not isinstance(uid, str) or not uid:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if not _manager.pool:
            return []

        await _ensure_threads_table(_manager.pool)

        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT 
                        thread_id,
                        title,
                        summary,
                        updated_at
                    FROM threads 
                    WHERE owner_uid = %s
                    ORDER BY updated_at DESC
                    LIMIT 20; 
                """, (uid,))
                
                rows = await cur.fetchall()
                
                history = []
                for row in rows:
                    thread_id = row[0]
                    title = row[1]
                    summary = row[2]
                    updated_at = row[3]
                    
                    history.append({
                        "id": thread_id,
                        "title": title or f"Session {thread_id[:8]}",
                        "updatedAt": updated_at.isoformat() if updated_at else None,
                        "timestamp": updated_at.isoformat() if updated_at else None,
                        "summary": summary
                    })
                
                return history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return []


@app.get("/api/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str, request: Request):
    """
    Retrieve message history for a specific thread.
    """
    try:
        uid = getattr(request.state, "user_uid", None)
        if not isinstance(uid, str) or not uid:
            raise HTTPException(status_code=401, detail="Unauthorized")

        await _ensure_thread_access(
            _manager.pool,
            thread_id=thread_id,
            uid=uid,
            create_if_missing=False,
        )

        graph = _manager.get_graph()

        config = _build_graph_config(thread_id, uid)
        state = await graph.aget_state(config)
        
        if not state.values:
            return []
        return _serialize_messages(state.values.get("messages", []))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch thread messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/threads/{thread_id}/snapshot")
async def get_thread_snapshot(thread_id: str, request: Request):
    """
    Retrieve a deterministic UI snapshot for a specific thread.
    """
    try:
        uid = getattr(request.state, "user_uid", None)
        if not isinstance(uid, str) or not uid:
            raise HTTPException(status_code=401, detail="Unauthorized")

        await _ensure_thread_access(
            _manager.pool,
            thread_id=thread_id,
            uid=uid,
            create_if_missing=False,
        )

        graph = _manager.get_graph()
        config = _build_graph_config(thread_id, uid)
        state = await graph.aget_state(config)

        if not state.values:
            return {
                "thread_id": thread_id,
                "messages": [],
                "plan": [],
                "artifacts": {},
                "ui_events": [],
            }

        return _build_snapshot_payload(thread_id, state.values)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch thread snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === In-painting Stub ===

class InpaintRequest(BaseModel):
    image_url: str = Field(..., description="Source image URL to edit")
    prompt: str = Field(..., min_length=1, description="Modification instruction")

async def _run_inpaint(
    image_url: str,
    prompt: str,
    session_id: str | None = None,
    slide_number: int | None = None,
) -> str:
    if not image_url:
        raise ValueError("image_url is required")

    reference_bytes = await asyncio.to_thread(download_blob_as_bytes, image_url)
    if not reference_bytes:
        raise ValueError("Failed to download source image")

    image_bytes, _ = await asyncio.to_thread(
        generate_image,
        prompt,
        seed=None,
        reference_image=reference_bytes,
        thought_signature=None,
    )

    public_url = await asyncio.to_thread(
        upload_to_gcs,
        image_bytes,
        content_type="image/png",
        session_id=session_id,
        slide_number=slide_number,
    )
    return public_url


@app.post("/api/image/{image_id}/inpaint")
async def inpaint_image(image_id: str, request: InpaintRequest):
    """
    Apply In-painting / Deep Edit to a generated image.
    """
    logger.info(f"In-painting request for {image_id}: {request.prompt}")
    try:
        new_url = await _run_inpaint(
            image_url=request.image_url,
            prompt=request.prompt,
            session_id=image_id,
            slide_number=None,
        )
        return {
            "success": True,
            "message": "In-painting completed.",
            "new_image_url": new_url,
            "original_image_id": image_id,
        }
    except ValueError as ve:
        logger.warning(f"In-painting validation failed: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"In-painting failed: {e}")
        raise HTTPException(status_code=500, detail="In-painting failed")


@app.post("/api/slide-deck/{deck_id}/slides/{slide_number}/inpaint")
async def inpaint_slide_deck(deck_id: str, slide_number: int, request: InpaintRequest):
    """
    Apply In-painting / Deep Edit to a specific slide in a deck.
    """
    logger.info(
        f"In-painting request for deck {deck_id} slide {slide_number}: "
        f"{request.prompt}"
    )
    try:
        new_url = await _run_inpaint(
            image_url=request.image_url,
            prompt=request.prompt,
            session_id=deck_id,
            slide_number=slide_number,
        )
        return {
            "success": True,
            "message": "In-painting completed.",
            "new_image_url": new_url,
            "deck_id": deck_id,
            "slide_number": slide_number,
        }
    except ValueError as ve:
        logger.warning(f"In-painting validation failed: {ve}")
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"In-painting failed: {e}")
        raise HTTPException(status_code=500, detail="In-painting failed")
