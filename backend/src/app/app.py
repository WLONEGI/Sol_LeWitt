"""
FastAPI application for Spell.
"""

import json
import logging
import base64
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import asyncio

from src.core.workflow import build_graph
from src.shared.config import TEAM_MEMBERS
from contextlib import asynccontextmanager
from src.core.workflow.service import run_agent_workflow, initialize_graph, close_graph

# Configure logging
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI app.
    Handles startup and shutdown events.
    """
    logger.info("🚀 Starting Spell API...")
    logger.info("Initializing application resources...")
    try:
        await initialize_graph()
        logger.info("✅ Application initialized successfully.")
    except Exception as e:
        logger.critical(f"❌ Application startup failed: {e}")
        raise e  # Ensure app crashes on startup if initialization fails
    yield
    logger.info("Cleaning up application resources...")
    await close_graph()
    logger.info("👋 Application shutdown complete.")

# Create FastAPI app
app = FastAPI(
    title="Spell API",
    description="API for Spell LangGraph-based agent workflow",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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

# Graph is now managed by service
# graph = build_graph()


class ContentItem(BaseModel):
    type: str = Field(..., description="The type of content (text, image, etc.)")
    text: str | None = Field(None, description="The text content if type is 'text'")
    image_url: str | None = Field(
        None, description="The image URL if type is 'image'"
    )


class ChatMessage(BaseModel):
    """Message format following Vercel AI SDK CoreMessage standard."""
    role: str = Field(
        ..., description="The role of the message sender (user or assistant)"
    )
    content: str | list[ContentItem] = Field(
        ...,
        description="The content of the message: either a string or a list of content items (SDK polymorphic format)",
    )


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., description="The conversation history")
    debug: bool = Field(False, description="Whether to enable debug logging")

    thread_id: str | None = Field(None, description="The thread ID for persistence")
    pptx_template_base64: str | None = Field(
        None, 
        description="Base64-encoded PPTX template file for design context extraction"
    )
    data: dict[str, Any] | None = Field(
        None,
        description="Additional data payload (e.g. from Vercel AI SDK 'data' field)"
    )


async def _extract_design_context(pptx_base64: str | None):
    """
    PPTXテンプレートからDesignContextを抽出する（AIワークフロー外の事前処理）
    
    Args:
        pptx_base64: Base64エンコードされたPPTXファイル
        
    Returns:
        DesignContext or None
    """
    if not pptx_base64:
        return None
    
    try:
        from src.domain.renderer.analyzer import analyze_pptx_template
        
        # Base64デコード
        pptx_bytes = base64.b64decode(pptx_base64)
        logger.info(f"Decoding PPTX template: {len(pptx_bytes)} bytes")
        
        # テンプレート解析（事前処理）
        design_context = await analyze_pptx_template(
            pptx_bytes,
            filename="uploaded_template.pptx",
            upload_to_gcs_enabled=True
        )
        
        logger.info(
            f"DesignContext extracted: {len(design_context.layouts)} layouts, "
            f"{len(design_context.layout_image_bytes)} layout images"
        )
        return design_context
        
    except ImportError as e:
        logger.warning(f"PPTX template analysis not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to extract design context: {e}")
        return None


@app.post("/api/chat/stream")
async def chat_endpoint(request: ChatRequest, req: Request):
    """
    Chat endpoint for LangGraph invoke.

    Args:
        request: The chat request
        req: The FastAPI request object for connection state checking

    Returns:
        The streamed response
    """
    try:
        # Convert Pydantic models to dictionaries and normalize content format
        messages = []
        for msg in request.messages:
            message_dict = {"role": msg.role}

            # Handle content (string or list of content items - SDK polymorphic format)
            if isinstance(msg.content, str):
                message_dict["content"] = msg.content
            else:
                # Content is a list of ContentItem
                content_items = []
                for item in msg.content:
                    if item.type == "text" and item.text:
                        content_items.append({"type": "text", "text": item.text})
                    elif item.type == "image" and item.image_url:
                        content_items.append(
                            {"type": "image", "image_url": item.image_url}
                        )
                message_dict["content"] = content_items if content_items else ""

            messages.append(message_dict)

        # [FIX] Deduplication Logic
        # If thread_id is present (continuation), only process the LAST message (User's new input).
        # Typically frontend sends full history [User, AI, User]. We only want the last 'User' message
        # because the previous ones are already in the DB state.
        if request.thread_id and len(messages) > 0:
            logger.info(f"Thread continuation ({request.thread_id}): processing only last message.")
            messages = [messages[-1]]


        # [NEW] PPTXテンプレートからDesignContextを抽出（事前処理）
        # request.dataもチェックする (Vercel SDKがdataフィールドに入れる場合があるため)
        pptx_b64 = request.pptx_template_base64
        if not pptx_b64 and request.data:
            pptx_b64 = request.data.get("pptx_template_base64")

        design_context = await _extract_design_context(pptx_b64)
        
        # [OPTIMIZATION] Clear Base64 data from State to prevent DB bloat.
        # Images are uploaded to GCS in `_extract_design_context` (via analyze_pptx_template),
        # so we rely on `layout_images` (URLs) instead of `layout_images_base64`.
        if design_context:
            logger.info("optimization: Clearing layout_images_base64 from DesignContext to save state size.")
            design_context.layout_images_base64 = {}
            design_context.default_template_image_base64 = None

        async def stream_generator():
            """
            Data Stream Protocol (Vercel AI SDK) 対応のストリームジェネレーター (JSON SSE)
            
            形式: data: {"type": "...", ...}
            Ref: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
            """
            from src.shared.utils.sse_formatter import DataStreamFormatter
            import uuid
            
            # フォーマッター初期化
            formatter = DataStreamFormatter()
            
            # State Management for Start/End events
            state = {
                "step_id": None,      # Current agent step ID
                "msg_id": None,       # Current text message ID
                "reasoning_id": None, # Current reasoning block ID
                "is_text_active": False,
                "is_reasoning_active": False
            }
            
            def check_and_close_text():
                """Close active text block if open."""
                if state["is_text_active"] and state["msg_id"]:
                    yield formatter.text_end(state["msg_id"])
                    state["is_text_active"] = False
                    state["msg_id"] = None

            def check_and_close_reasoning():
                """Close active reasoning block if open."""
                if state["is_reasoning_active"] and state["reasoning_id"]:
                    yield formatter.reasoning_end(state["reasoning_id"])
                    state["is_reasoning_active"] = False
                    state["reasoning_id"] = None

            try:
                # [NEW] Pre-analysis status
                if pptx_b64:
                    yield formatter.data_part(
                        "data-status",
                        {"message": "Analyzing template...", "phase": "preprocessing"}
                    )

                async for event_json in run_agent_workflow(
                    messages,
                    request.debug,
                    request.thread_id,
                    design_context=design_context,
                ):
                    if await req.is_disconnected():
                        logger.info("Client disconnected, stopping workflow")
                        break

                    try:
                        event = json.loads(event_json)
                        evt_type = event.get("type")
                        content = event.get("content")
                        metadata = event.get("metadata", {})
                        
                        logger.debug(f"Stream processing event: {evt_type}")

                        # --- 1. System / Step Events ---
                        if evt_type == "agent_start":
                            # Close previous blocks if any (shouldn't happen if cleanly ended)
                            for chunk in check_and_close_text(): yield chunk
                            for chunk in check_and_close_reasoning(): yield chunk
                            
                            step_id = metadata.get("run_id") or f"step_{uuid.uuid4().hex[:8]}"
                            state["step_id"] = step_id
                            state["msg_id"] = f"msg_{step_id}" # Associate message with step
                            state["reasoning_id"] = f"rs_{step_id}"
                            
                            yield formatter.step_start(step_id)
                            # Agent status update for UI Timeline
                            yield formatter.data_part("data-agent-start", {
                                "agent_name": metadata.get("name", "unknown"),
                                "id": step_id,
                                "title": metadata.get("title", f"Agent: {metadata.get('name')}"),
                                "description": metadata.get("description", "")
                            })

                        elif evt_type == "agent_end":
                            for chunk in check_and_close_text(): yield chunk
                            for chunk in check_and_close_reasoning(): yield chunk
                            
                            if state["step_id"]:
                                yield formatter.step_finish(state["step_id"])
                                # Signal end for UI Timeline
                                yield formatter.data_part("data-agent-end", {
                                    "status": "completed",
                                    "stepId": state["step_id"]
                                })
                                state["step_id"] = None

                        # --- 2. Text & Reasoning ---
                        elif evt_type == "message_delta":
                            # Ensure reasoning is closed before text (if interleaved, close/reopen needed, 
                            # but usually they are sequential or distinct)
                            for chunk in check_and_close_reasoning(): yield chunk
                            
                            if not state["is_text_active"]:
                                # Start text block
                                if not state["msg_id"]: state["msg_id"] = f"msg_{uuid.uuid4().hex[:8]}"
                                yield formatter.text_start(state["msg_id"])
                                state["is_text_active"] = True
                            
                            yield formatter.text_delta(state["msg_id"], content)
                        
                        elif evt_type == "reasoning_delta":
                            for chunk in check_and_close_text(): yield chunk
                            
                            if not state["is_reasoning_active"]:
                                if not state["reasoning_id"]: state["reasoning_id"] = f"rs_{uuid.uuid4().hex[:8]}"
                                yield formatter.reasoning_start(state["reasoning_id"])
                                state["is_reasoning_active"] = True
                                
                            yield formatter.reasoning_delta(state["reasoning_id"], content)

                        # --- 3. Artifacts & Custom Data ---
                        elif evt_type == "plan_update":
                            # Supervisor: Plan update
                            # If content is a list of steps, send as data-plan-update
                            yield formatter.data_part("data-plan-update", content)
                            
                        elif evt_type == "artifact_open":
                            # Storywriter/Visualizer: Loading state
                            yield formatter.data_part("data-artifact-open", content)
                        
                        elif evt_type == "artifact_ready":
                            # Storywriter/Visualizer: Finished artifact
                            # Visualizer may output image URL -> use file_part for native support
                            # Storywriter outputs JSON -> data_part
                            if isinstance(content, dict) and content.get("kind") == "image":
                                yield formatter.file_part(content.get("url"), "image/png")
                            else:
                                yield formatter.data_part("data-artifact-ready", content)
                                
                        elif evt_type == "sources":
                            # Researcher: Sources
                            # Content list of source dicts
                            if isinstance(content, list):
                                for src in content:
                                    yield formatter.source_url(
                                        source_id=f"src_{uuid.uuid4().hex[:4]}",
                                        url=src.get("url", "")
                                    )

                        # --- 4. Tool Execution (DataAnalyst) ---
                        elif evt_type == "tool_call":
                            # Close text/reasoning
                            for chunk in check_and_close_text(): yield chunk
                            for chunk in check_and_close_reasoning(): yield chunk
                            
                            # DataAnalyst: Code Block as Artifact
                            # User requested data-code-execution ONLY to avoid double UI
                            tool_id = metadata.get("run_id", f"call_{uuid.uuid4().hex[:8]}")
                            cmd_args = content.get("input", {})
                            
                            yield formatter.data_part("data-code-execution", {
                                "toolCallId": tool_id,
                                "code": cmd_args.get("code") or cmd_args.get("query"),
                                "language": "python" # Assumption
                            })

                        elif evt_type == "tool_result":
                            tool_id = metadata.get("run_id", f"call_{uuid.uuid4().hex[:8]}")
                            yield formatter.data_part("data-code-output", {
                                "toolCallId": tool_id,
                                "result": content.get("result")
                            })

                        # --- 5. Other ---
                        elif evt_type == "progress":
                            yield formatter.data_part("data-progress", {"message": content, **metadata})

                        elif evt_type == "workflow_start":
                            yield formatter.data_part("data-workflow-start", {"runId": metadata.get("run_id")})

                        elif evt_type == "data-title-generated":
                            yield formatter.data_part("data-title-generated", content)

                        elif evt_type and evt_type.startswith("data-"):
                            # Forward custom data events directly
                            yield formatter.data_part(evt_type, content)


                            
                        else:
                            # Generic data fallback
                            logger.debug(f"Unhandled event type mapped to data: {evt_type}")
                            yield formatter.data_part("data-unknown", event)

                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse event JSON: {event_json}")
                        continue
                
                # [Finalization]
                for chunk in check_and_close_text(): yield chunk
                for chunk in check_and_close_reasoning(): yield chunk

                yield formatter.finish()
                # Yield DONE marker is optional in generator if handled by server framer, 
                # but sse_starlette usually handles it. 
                # AI SDK expects `data: [DONE]`. 
                # Since we use StreamingResponse with media_type="text/event-stream", 
                # we should yield the raw string from formatter.done()?
                # No, StreamingResponse yields chunks. formatter.done() returns string.
                # But typically `finish` event is enough for AI SDK to close.
                # We'll emit it just in case.
                yield formatter.done()
                        
            except asyncio.CancelledError:
                logger.info("Stream processing cancelled")
                raise
            except Exception as e:
                # Error event
                yield formatter.error(str(e))
                logger.error(f"Stream error: {e}")

        from fastapi.responses import StreamingResponse
        from src.shared.utils.sse_formatter import create_sse_headers
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers=create_sse_headers()
        )

    except ValueError as e:
        logger.error(f"Invalid request data: {e}")
        raise HTTPException(status_code=400, detail=f"Invalid request: {str(e)}")
    except HTTPException as e:
        raise e  # Re-raise HTTPExceptions (like from helpers)
    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}


@app.post("/api/template/analyze")
async def analyze_template_endpoint(file: UploadFile = File(...)):
    """
    PPTXテンプレートを解析してDesignContextを返すエンドポイント
    
    このエンドポイントは、テンプレートの事前解析に使用できます。
    フロントエンドでテンプレートをアップロードし、解析結果を
    キャッシュして後続のchatリクエストで使用できます。
    
    Args:
        file: アップロードされたPPTXファイル
        
    Returns:
        解析結果（JSON形式のDesignContext）
    """
    if not file.filename or not file.filename.endswith(('.pptx', '.PPTX')):
        raise HTTPException(
            status_code=400, 
            detail="Invalid file type. Please upload a .pptx file."
        )
    
    try:
        from src.domain.renderer.analyzer import analyze_pptx_template
        
        # ファイル読み込み
        pptx_bytes = await file.read()
        logger.info(f"Received PPTX template: {file.filename} ({len(pptx_bytes)} bytes)")
        
        # テンプレート解析
        design_context = await analyze_pptx_template(
            pptx_bytes,
            filename=file.filename,
            upload_to_gcs_enabled=True
        )
        
        # レスポンス生成（layout_image_bytesは除外される）
        return {
            "success": True,
            "filename": file.filename,
            "design_context": design_context.model_dump(mode="json"),
            "summary": {
                "layouts_count": len(design_context.layouts),
                "layout_types": [l.layout_type for l in design_context.layouts],
                "color_scheme": {
                    "accent1": design_context.color_scheme.accent1,
                    "accent2": design_context.color_scheme.accent2,
                },
                "font_scheme": {
                    "major": design_context.font_scheme.major_latin,
                    "minor": design_context.font_scheme.minor_latin,
                }
            }
        }
        
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"PPTX template analysis dependencies not installed: {e}"
        )
    except Exception as e:
        logger.error(f"Error analyzing template: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze template: {str(e)}"
        )


# --- [NEW] Features: History & In-painting ---

@app.get("/api/history")
async def get_history(uid: str | None = None):
    """
    Get conversation history from the threads table.
    
    Returns:
        List of session summaries.
    """
    try:
        from src.core.workflow.service import _manager
        
        if not _manager.pool:
            return []

        async with _manager.pool.connection() as conn:
             async with conn.cursor() as cur:
                # Query threads table
                await cur.execute("""
                    SELECT 
                        thread_id,
                        title,
                        summary,
                        created_at
                    FROM threads 
                    ORDER BY updated_at DESC
                    LIMIT 20; 
                """)
                
                rows = await cur.fetchall()
                
                history = []
                for row in rows:
                    thread_id = row[0]
                    title = row[1]
                    summary = row[2]
                    created_at = row[3]
                    
                    history.append({
                        "id": thread_id,
                        "title": title or f"Session {thread_id[:8]}",
                        "timestamp": created_at.isoformat() if created_at else None,
                        "summary": summary
                    })
                
                return history

    except Exception as e:
        logger.error(f"Failed to fetch history: {e}")
        return []


@app.get("/api/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    """
    Retrieve message history for a specific thread.
    """
    try:
        from src.core.workflow.service import _manager
        graph = _manager.get_graph()
        
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        
        if not state.values:
            return []
            
        messages = state.values.get("messages", [])
        
        # Convert LangChain messages to our API format
        formatted_messages = []
        for msg in messages:
            # Handle different message types (HumanMessage, AIMessage, etc.)
            role = "user"
            if msg.type == "ai":
                role = "assistant"
            elif msg.type == "human":
                role = "user"
            elif msg.type == "system":
                role = "system"
            elif msg.type == "tool":
                continue # Skip tool outputs for chat view? Or show them? 
                         # Usually we hide tool outputs in main chat unless needed.
            
            # Extract content
            content = msg.content
            if isinstance(content, list):
                 # simplify for now
                 text_parts = [c["text"] for c in content if "text" in c]
                 content = "".join(text_parts)
            
            # Extract metadata (e.g. sources, ui_type)
            additional_kwargs = msg.additional_kwargs or {}
            sources = additional_kwargs.get("sources", [])
            ui_type = additional_kwargs.get("ui_type") 
            
            # [NEW] Extract reasoning if available (for collapsible thought)
            # Some providers put it in additional_kwargs, others might differ.
            reasoning = additional_kwargs.get("reasoning_content")

            formatted_messages.append({
                "role": role,
                "content": content,
                "sources": sources,
                "name": msg.name,
                "id": msg.id if hasattr(msg, "id") else None,
                # [NEW] Custom fields for rich history
                "ui_type": ui_type,
                "metadata": additional_kwargs, # Pass full metadata for Plan/Artifact data
                "reasoning": reasoning 
            })
            
        return formatted_messages
        
    except Exception as e:
        logger.error(f"Failed to fetch thread messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class InpaintRequest(BaseModel):
    rect: dict[str, float] = Field(..., description="Selection rectangle {x, y, w, h}")
    prompt: str = Field(..., description="Modification instruction")


@app.post("/api/image/{image_id}/inpaint")
async def inpaint_image(image_id: str, request: InpaintRequest):
    """
    Apply In-painting / Deep Edit to a generated image.
    
    Args:
        image_id: ID (or URL/filename) of the target image.
        request: Inpaint parameters.
        
    Returns:
        JSON with new image information or confirmation.
    """
    logger.info(f"In-painting request for {image_id}: {request.prompt} at {request.rect}")
    
    # TODO: Integrate with backend agent/tool.
    # Options:
    # 1. Direct call to Vertex AI Imagen 2 Edit API.
    # 2. Trigger a LangGraph run with "Modify Slide X..." instruction.
    
    # For Phase 1, we acknowledge the request. 
    # Real implementation requires 'image_service' (TBD).
    
    return {
        "success": True,
        "message": "In-painting request received (Backend stub).",
        "new_image_url": None, # Should return new URL when implemented
        "original_image_id": image_id
    }

