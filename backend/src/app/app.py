"""
FastAPI application for Spell - LangServe Edition.
Uses langserve add_routes for standard LangGraph API exposure.
"""

import json
import logging
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

from langserve import add_routes

from src.core.workflow.service import initialize_graph, close_graph, _manager

# Configure logging
logger = logging.getLogger(__name__)


# === LangServe Input/Output Schemas ===

class ChatInput(BaseModel):
    """Input schema for LangServe chat endpoint.
    
    Follows Vercel AI SDK CoreMessage format for messages.
    """
    messages: list[dict[str, Any]] = Field(
        ..., 
        description="List of messages in the conversation"
    )


class ChatOutput(BaseModel):
    """Output schema for LangServe - LangGraph returns full state."""
    messages: list[Any] = Field(default_factory=list)
    plan: list[Any] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)


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
            return config

        add_routes(
            app,
            graph_with_types,
            path="/api/chat",
            enabled_endpoints=["stream_events"],  # POST /api/chat/stream_events
            per_req_config_modifier=per_req_config_modifier,
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


# === Health Check ===

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "ok"}


# === History Endpoints ===

@app.get("/api/history")
async def get_history(uid: str | None = None):
    """
    Get conversation history from the threads table.
    """
    try:
        if not _manager.pool:
            return []

        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
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
        graph = _manager.get_graph()
        
        config = {"configurable": {"thread_id": thread_id}}
        state = await graph.aget_state(config)
        
        if not state.values:
            return []
            
        messages = state.values.get("messages", [])
        
        # Convert LangChain messages to our API format
        formatted_messages = []
        for msg in messages:
            role = "user"
            if msg.type == "ai":
                role = "assistant"
            elif msg.type == "human":
                role = "user"
            elif msg.type == "system":
                role = "system"
            elif msg.type == "tool":
                continue 
            
            content = msg.content
            if isinstance(content, list):
                text_parts = [c["text"] for c in content if "text" in c]
                content = "".join(text_parts)
            
            additional_kwargs = msg.additional_kwargs or {}
            sources = additional_kwargs.get("sources", [])
            ui_type = additional_kwargs.get("ui_type") 
            reasoning = additional_kwargs.get("reasoning_content")

            formatted_messages.append({
                "role": role,
                "content": content,
                "sources": sources,
                "name": msg.name,
                "id": msg.id if hasattr(msg, "id") else None,
                "ui_type": ui_type,
                "metadata": additional_kwargs, 
                "reasoning": reasoning 
            })
            
        return formatted_messages
        
    except Exception as e:
        logger.error(f"Failed to fetch thread messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# === In-painting Stub ===

class InpaintRequest(BaseModel):
    rect: dict[str, float] = Field(..., description="Selection rectangle {x, y, w, h}")
    prompt: str = Field(..., description="Modification instruction")


@app.post("/api/image/{image_id}/inpaint")
async def inpaint_image(image_id: str, request: InpaintRequest):
    """
    Apply In-painting / Deep Edit to a generated image.
    """
    logger.info(f"In-painting request for {image_id}: {request.prompt} at {request.rect}")
    return {
        "success": True,
        "message": "In-painting request received (Backend stub).",
        "new_image_url": None, 
        "original_image_id": image_id
    }
