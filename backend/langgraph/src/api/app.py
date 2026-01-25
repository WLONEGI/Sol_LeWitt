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

from src.graph import build_graph
from src.config import TEAM_MEMBERS
from contextlib import asynccontextmanager
from src.service.workflow_service import run_agent_workflow, initialize_graph, close_graph

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
        from src.utils.template_analyzer import analyze_pptx_template
        
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

        # [NEW] PPTXテンプレートからDesignContextを抽出（事前処理）
        # request.dataもチェックする (Vercel SDKがdataフィールドに入れる場合があるため)
        pptx_b64 = request.pptx_template_base64
        if not pptx_b64 and request.data:
            pptx_b64 = request.data.get("pptx_template_base64")

        design_context = await _extract_design_context(pptx_b64)

        async def stream_generator():
            """
            UI Message Stream Protocol (AI SDK v6) 対応のストリームジェネレーター
            
            形式: data: {JSON}\n\n (標準SSE形式)
            """
            from src.utils.sse_formatter import UIMessageStreamFormatter
            
            # フォーマッター初期化
            formatter = UIMessageStreamFormatter()
            
            try:
                # メッセージ開始
                yield formatter.start_message()
                
                # [NEW] Pre-analysis "Thinking" - Analyzing template
                if pptx_b64:
                    yield formatter.custom_data(
                        "status", 
                        {"message": "Analyzing template...", "phase": "preprocessing"},
                        transient=True
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
                        
                        logger.info(f"Stream processing event: {evt_type}")

                        if evt_type == "message_delta":
                            # テキストデルタ → text-delta
                            yield formatter.text_delta(content)
                        
                        elif evt_type == "reasoning_delta":
                            # 推論プロセス → reasoning-delta
                            yield formatter.reasoning_delta(content)
                            
                        elif evt_type == "artifact":
                            # アーティファクト → data-artifact
                            yield formatter.custom_data("artifact", content)
                        
                        elif evt_type == "workflow_start":
                            # ワークフロー開始 → data-workflow
                            yield formatter.custom_data("workflow", {
                                "status": "started",
                                **metadata
                            })
                             
                        elif evt_type == "agent_start":
                            # エージェント開始 → data-agent
                            yield formatter.custom_data("agent", {
                                "status": "started",
                                **metadata
                            })
                        
                        elif evt_type == "agent_end":
                            # エージェント終了 → data-agent
                            yield formatter.custom_data("agent", {
                                "status": "completed",
                                **metadata
                            })
                             
                        elif evt_type == "progress":
                            # 進捗状況 → data-progress
                            logger.info(f"Yielding progress event: {content}")
                            yield formatter.custom_data("progress", {
                                "content": content,
                                **metadata
                            })

                        elif evt_type == "tool_call":
                            # ツール呼び出し → tool-call (SDK標準)
                            tool_call_id = metadata.get("run_id", f"call-{id(content)}")
                            yield formatter.tool_call(
                                tool_call_id=tool_call_id,
                                tool_name=content.get("tool_name", "unknown"),
                                args=content.get("input", {})
                            )
                        
                        elif evt_type == "tool_result":
                            # ツール結果 → tool-result (SDK標準)
                            tool_call_id = metadata.get("run_id", f"call-{id(content)}")
                            yield formatter.tool_result(
                                tool_call_id=tool_call_id,
                                tool_name=content.get("tool_name", "unknown"),
                                result=content.get("result", "")
                            )

                        elif evt_type == "sources":
                            # ソース/引用 → source-url
                            if isinstance(content, list):
                                for i, source in enumerate(content):
                                    if isinstance(source, str):
                                        yield formatter.source_url(
                                            source_id=f"src-{i}",
                                            url=source
                                        )
                                    elif isinstance(source, dict):
                                        yield formatter.source_url(
                                            source_id=source.get("id", f"src-{i}"),
                                            url=source.get("url", ""),
                                            title=source.get("title")
                                        )

                        else:
                            logger.info(f"Unhandled event type: {evt_type}")

                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse event JSON: {event_json}")
                        continue
                
                # 正常終了
                yield formatter.finish()
                        
            except asyncio.CancelledError:
                logger.info("Stream processing cancelled")
                raise
            except Exception as e:
                # ストリーム内でエラーを通知（UI Message Stream形式）
                yield formatter.error(str(e), code="STREAM_ERROR")
                logger.error(f"Stream error: {e}")

        from fastapi.responses import StreamingResponse
        from src.utils.sse_formatter import create_sse_headers
        
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
        from src.utils.template_analyzer import analyze_pptx_template
        
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
    Get conversation history from the checkpoints table.
    
    Returns:
        List of session summaries.
    """
    try:
        from src.service.workflow_service import _manager
        
        if not _manager.pool:
            # Fallback if pool is not initialized (e.g. dev mode without DB)
            return []

        # Query to get distinct thread_ids and their latest checkpoint timestamp
        # LangGraph Postgres Checkpointer uses table 'checkpoints'
        # Columns: thread_id, checkpoint_id, checkpoint, metadata, parent_checkpoint_id
        
        # We want to list unique threads.
        # Ideally, we should have a separate 'threads' table, but for now we query checkpoints.
        # We group by thread_id and order by max(checkpoint_id) (which implies time).
        
        async with _manager.pool.connection() as conn:
             async with conn.cursor() as cur:
                # Optimized query to get unique threads and their last activity
                # Note: This might be slow on huge datasets without index on thread_id
                await cur.execute("""
                    SELECT 
                        thread_id,
                        MAX(checkpoint_id) as last_checkpoint
                    FROM checkpoints 
                    GROUP BY thread_id
                    ORDER BY last_checkpoint DESC
                    LIMIT 20; 
                """)
                # TODO: Retrieve 'summary' or 'title' from metadata if available.
                # For now, we just return the thread_id.
                
                rows = await cur.fetchall()
                
                history = []
                for row in rows:
                    thread_id = row[0]
                    # We could fetch extra metadata here if needed
                    history.append({
                        "id": thread_id,
                        "title": f"Session {thread_id[:8]}...", # Fallback title
                        "timestamp": "2024-01-01T00:00:00Z", # Placeholder or parse checkpoint_id if it's a ULID?
                        "summary": "No summary available"
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
        from src.service.workflow_service import _manager
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

