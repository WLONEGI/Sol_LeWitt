"""
FastAPI application for Sol LeWitt - LangServe Edition.
Uses langserve add_routes for standard LangGraph API exposure.
"""

import json
import os
import logging
import asyncio
import base64
import mimetypes
import re
import uuid
import time
import random
from typing import Any, Optional, Literal
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
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
from src.core.workflow.step_v2 import normalize_plan_v2
from src.infrastructure.auth.firebase import verify_firebase_token
from src.infrastructure.auth.user_store import upsert_user
from src.domain.designer.generator import generate_image
from src.domain.designer.pptx_parser import extract_pptx_context
from src.infrastructure.llm.llm import is_rate_limited_error
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
_STREAM_BENCH_ENABLED = os.getenv("STREAM_BENCH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
try:
    _STREAM_BENCH_SAMPLE_RATE = float(os.getenv("STREAM_BENCH_SAMPLE_RATE", "1.0"))
except Exception:
    _STREAM_BENCH_SAMPLE_RATE = 1.0
_STREAM_BENCH_SAMPLE_RATE = max(0.0, min(1.0, _STREAM_BENCH_SAMPLE_RATE))
_STREAM_UI_EVENT_FILTER_ENABLED = os.getenv("STREAM_UI_EVENT_FILTER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
MAX_UPLOAD_FILES = 5
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PPTX_UPLOAD_BYTES = 40 * 1024 * 1024
MAX_DOCUMENT_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_INPAINT_REFERENCE_IMAGES = 3
_ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
_ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
_ALLOWED_PDF_CONTENT_TYPES = {"application/pdf"}
_ALLOWED_PDF_EXTENSIONS = {".pdf"}
_ALLOWED_TEXT_CONTENT_TYPES = {"text/plain", "text/markdown", "text/x-markdown"}
_ALLOWED_TEXT_EXTENSIONS = {".txt", ".md"}
_ALLOWED_CSV_CONTENT_TYPES = {"text/csv", "application/csv"}
_ALLOWED_CSV_EXTENSIONS = {".csv"}
_ALLOWED_JSON_CONTENT_TYPES = {"application/json", "text/json"}
_ALLOWED_JSON_EXTENSIONS = {".json"}
_ALLOWED_PPTX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/octet-stream",
}
_ALLOWED_PPTX_EXTENSIONS = {".pptx"}
_DISALLOWED_XLSX_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/vnd.ms-excel.sheet.macroenabled.12",
}
_DISALLOWED_XLSX_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".xlsb"}

# === LangServe Input/Output Schemas ===

class ChatInput(BaseModel):
    """Inner input schema for the graph state.
    This corresponds to the fields in the State TypedDict.
    """
    messages: list[Any] = Field(..., description="List of input messages")
    selected_image_inputs: list[dict[str, Any]] = Field(
        default_factory=list,
        description="ユーザーが明示的に指定した参照画像入力（次Worker入力用）"
    )
    interrupt_intent: bool = Field(
        default=False,
        description="実行中にユーザーが送信した割り込み指示かどうか"
    )
    product_type: Optional[Literal["slide", "design", "comic"]] = Field(
        default=None,
        description="初回リクエスト時に固定する制作カテゴリ"
    )
    aspect_ratio: Optional[str] = Field(
        default=None,
        description="User-selected aspect ratio (e.g., '16:9', '1:1')"
    )
    attachments: list[dict[str, Any]] = Field(
        default_factory=list,
        description="ユーザー添付ファイルのメタデータ一覧"
    )
    pptx_template_base64: Optional[str] = Field(
        default=None,
        description="後方互換用のPPTXテンプレート(base64)"
    )

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
                        product_type TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    """
                )
                await cur.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS owner_uid TEXT;")
                await cur.execute("ALTER TABLE threads ADD COLUMN IF NOT EXISTS product_type TEXT;")
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
    product_type: str | None = None,
) -> None:
    if not thread_id:
        raise HTTPException(status_code=400, detail="thread_id is required")
    if not pool:
        raise HTTPException(status_code=503, detail="Database not initialized")

    await _ensure_threads_table(pool)
    logger.info(f"[_ensure_thread_access] thread_id={thread_id}, product_type={product_type}, create_if_missing={create_if_missing}")

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
                    # Update timestamp and product_type if provided
                    if product_type:
                        await cur.execute(
                            "UPDATE threads SET updated_at = NOW(), product_type = %s WHERE thread_id = %s",
                            (product_type, thread_id),
                        )
                    else:
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
                INSERT INTO threads (thread_id, owner_uid, title, summary, product_type, created_at, updated_at)
                VALUES (%s, %s, NULL, '', %s, NOW(), NOW())
                ON CONFLICT (thread_id) DO NOTHING;
                """,
                (thread_id, uid, product_type),
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
    logger.info("🚀 Starting Sol LeWitt API (LangServe Edition)...")
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
            enabled_endpoints=["invoke", "batch", "stream_log"], # Explicitly exclude stream and stream_events to use custom handlers
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
    title="Sol LeWitt API",
    description="API for Sol LeWitt LangGraph-based agent workflow (LangServe Edition)",
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
    if path.startswith("/api/files/"):
        return True
    if path.startswith("/api/image/"):
        return True
    if path.startswith("/api/slide-deck/"):
        return True
    return False


def _sanitize_filename(filename: str) -> str:
    base = os.path.basename(filename or "upload").strip()
    stem, ext = os.path.splitext(base)

    # `.pptx` のような先頭ドットのみの名前は splitext で拡張子扱いされないため補正する。
    if not ext and stem.startswith(".") and stem.count(".") == 1:
        ext = stem
        stem = ""

    safe_stem = re.sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("._-")
    safe_ext = re.sub(r"[^a-zA-Z0-9.]+", "", ext).lower()
    if safe_ext and not safe_ext.startswith("."):
        safe_ext = f".{safe_ext}"

    if safe_stem:
        return f"{safe_stem}{safe_ext}"
    if safe_ext:
        return f"upload{safe_ext}"
    return "upload"


def _normalize_display_filename(filename: str, fallback: str = "upload") -> str:
    raw = str(filename or "")
    base = raw.replace("\\", "/").split("/")[-1].strip()
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    if base in {"", ".", ".."}:
        return fallback
    return base[:255]


def _normalize_session_key(raw: str | None, fallback: str) -> str:
    source = raw if isinstance(raw, str) and raw.strip() else fallback
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", source).strip("_")
    return normalized[:120] or "session"


def _infer_upload_kind(content_type: str | None, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    normalized_content_type = (content_type or "").lower()

    if ext in _DISALLOWED_XLSX_EXTENSIONS or normalized_content_type in _DISALLOWED_XLSX_CONTENT_TYPES:
        return "xlsx_unsupported"
    if ext in _ALLOWED_PPTX_EXTENSIONS:
        return "pptx"
    if normalized_content_type in _ALLOWED_IMAGE_CONTENT_TYPES or ext in _ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if normalized_content_type in _ALLOWED_PDF_CONTENT_TYPES or ext in _ALLOWED_PDF_EXTENSIONS:
        return "pdf"
    if normalized_content_type in _ALLOWED_CSV_CONTENT_TYPES or ext in _ALLOWED_CSV_EXTENSIONS:
        return "csv"
    if normalized_content_type in _ALLOWED_JSON_CONTENT_TYPES or ext in _ALLOWED_JSON_EXTENSIONS:
        return "json"
    if normalized_content_type in _ALLOWED_TEXT_CONTENT_TYPES or ext in _ALLOWED_TEXT_EXTENSIONS:
        return "text"
    if normalized_content_type in _ALLOWED_PPTX_CONTENT_TYPES:
        return "pptx"
    return "other"


def _validate_upload_file(
    *,
    content_type: str | None,
    filename: str,
    size_bytes: int,
) -> str:
    kind = _infer_upload_kind(content_type, filename)
    normalized_content_type = (content_type or "").lower()
    ext = os.path.splitext(filename)[1].lower()

    if kind == "xlsx_unsupported":
        raise HTTPException(
            status_code=415,
            detail="XLSX/XLS is excluded because Gemini 3 input format does not directly support spreadsheet binaries.",
        )

    if kind == "image":
        if normalized_content_type and normalized_content_type not in _ALLOWED_IMAGE_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported image content type: {content_type}")
        if ext and ext not in _ALLOWED_IMAGE_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported image extension: {ext}")
        if size_bytes > MAX_IMAGE_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image file is too large (max 10MB)")
        return kind

    if kind == "pptx":
        if ext not in _ALLOWED_PPTX_EXTENSIONS:
            raise HTTPException(status_code=415, detail="Only .pptx is allowed for presentation files")
        if normalized_content_type and normalized_content_type not in _ALLOWED_PPTX_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported pptx content type: {content_type}")
        if size_bytes > MAX_PPTX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PPTX file is too large (max 40MB)")
        return kind

    if kind == "pdf":
        if ext and ext not in _ALLOWED_PDF_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported pdf extension: {ext}")
        if normalized_content_type and normalized_content_type not in _ALLOWED_PDF_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported pdf content type: {content_type}")
        if size_bytes > MAX_DOCUMENT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="PDF file is too large (max 20MB)")
        return kind

    if kind == "csv":
        if ext and ext not in _ALLOWED_CSV_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported csv extension: {ext}")
        if (
            normalized_content_type
            and normalized_content_type not in _ALLOWED_CSV_CONTENT_TYPES
            and not (ext in _ALLOWED_CSV_EXTENSIONS and normalized_content_type == "text/plain")
        ):
            raise HTTPException(status_code=415, detail=f"Unsupported csv content type: {content_type}")
        if size_bytes > MAX_DOCUMENT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="CSV file is too large (max 20MB)")
        return kind

    if kind == "json":
        if ext and ext not in _ALLOWED_JSON_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported json extension: {ext}")
        if (
            normalized_content_type
            and normalized_content_type not in _ALLOWED_JSON_CONTENT_TYPES
            and not (ext in _ALLOWED_JSON_EXTENSIONS and normalized_content_type == "text/plain")
        ):
            raise HTTPException(status_code=415, detail=f"Unsupported json content type: {content_type}")
        if size_bytes > MAX_DOCUMENT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="JSON file is too large (max 20MB)")
        return kind

    if kind == "text":
        if ext and ext not in _ALLOWED_TEXT_EXTENSIONS:
            raise HTTPException(status_code=415, detail=f"Unsupported text extension: {ext}")
        if normalized_content_type and normalized_content_type not in _ALLOWED_TEXT_CONTENT_TYPES:
            raise HTTPException(status_code=415, detail=f"Unsupported text content type: {content_type}")
        if size_bytes > MAX_DOCUMENT_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Text/Markdown file is too large (max 20MB)")
        return kind

    raise HTTPException(
        status_code=415,
        detail="Unsupported file type. Allowed: image(jpg/png/webp), pptx, pdf, csv, txt/md, json (xlsx excluded).",
    )


def _is_pptx_attachment(item: dict[str, Any]) -> bool:
    kind = str(item.get("kind") or "").lower()
    if kind == "pptx":
        return True
    filename = str(item.get("filename") or "").lower()
    mime_type = str(item.get("mime_type") or "").lower()
    if filename.endswith(".pptx"):
        return True
    return mime_type in _ALLOWED_PPTX_CONTENT_TYPES


def _decode_base64_payload(raw: str) -> bytes | None:
    payload = raw.strip()
    if not payload:
        return None
    if "," in payload and payload.lower().startswith("data:"):
        payload = payload.split(",", 1)[1]
    try:
        return base64.b64decode(payload, validate=False)
    except Exception:
        return None


async def _build_pptx_context(
    *,
    attachments: list[dict[str, Any]],
    pptx_template_base64: str | None,
) -> dict[str, Any] | None:
    templates: list[dict[str, Any]] = []

    for item in attachments:
        if not isinstance(item, dict):
            continue
        if not _is_pptx_attachment(item):
            continue
        source_url = item.get("url")
        if not isinstance(source_url, str) or not source_url:
            continue
        filename = item.get("filename") if isinstance(item.get("filename"), str) else None
        try:
            payload = await asyncio.to_thread(download_blob_as_bytes, source_url)
            if not payload:
                logger.warning("Failed to download PPTX attachment: %s", source_url)
                continue
            parsed = await asyncio.to_thread(
                extract_pptx_context,
                payload,
                filename=filename,
                source_url=source_url,
            )
            templates.append(parsed)
        except Exception as exc:
            logger.warning("Failed to parse PPTX attachment %s: %s", source_url, exc)

    if not templates and isinstance(pptx_template_base64, str) and pptx_template_base64.strip():
        decoded = _decode_base64_payload(pptx_template_base64)
        if decoded:
            try:
                parsed = await asyncio.to_thread(
                    extract_pptx_context,
                    decoded,
                    filename="legacy_template.pptx",
                    source_url=None,
                )
                templates.append(parsed)
            except Exception as exc:
                logger.warning("Failed to parse legacy pptx_template_base64: %s", exc)

    if not templates:
        return None

    return {
        "template_count": len(templates),
        "primary": templates[0],
        "templates": templates,
    }


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path == "/api/chat/stream":
        return JSONResponse(
            status_code=410,
            content={"detail": "Deprecated endpoint. Use /api/chat/stream_events."},
        )

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

@app.post("/api/chat/stream")
async def deprecated_chat_stream_endpoint():
    raise HTTPException(
        status_code=410,
        detail="Deprecated endpoint. Use /api/chat/stream_events.",
    )


def _compact_stream_metadata(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}

    compact: dict[str, Any] = {}
    for key in ("run_name", "langgraph_node", "langgraph_checkpoint_ns", "checkpoint_ns"):
        value = raw.get(key)
        if value is None:
            continue
        compact[key] = value
    return compact


def _encode_sse_payload(payload: dict[str, Any]) -> str:
    return (
        "data: "
        + json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=langserve.serialization.default,
        )
        + "\n\n"
    )


_ALLOWED_DATA_CUSTOM_EVENTS: set[str] = {
    "data-plan_update",
    "data-plan_step_started",
    "data-plan_step_ended",
    "data-outline",
    "data-title-update",
    "data-coordinator-response",
    "data-coordinator-followups",
    "data-visual-plan",
    "data-visual-prompt",
    "data-visual-image",
    "data-visual-pdf",
    "data-analyst-start",
    "data-analyst-code-delta",
    "data-analyst-log-delta",
    "data-analyst-output",
    "data-analyst-complete",
    "data-writer-output",
    "data-research-start",
    "data-research-token",
    "data-research-complete",
    "data-research-report",
}

_ALLOWED_LEGACY_CUSTOM_EVENTS: set[str] = {
    "writer-output",
    "plan_update",
    "title_generated",
    "research_worker_start",
    "research_worker_token",
    "research_worker_complete",
}


def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _should_collect_stream_bench() -> bool:
    if not _STREAM_BENCH_ENABLED:
        return False
    if _STREAM_BENCH_SAMPLE_RATE >= 1.0:
        return True
    if _STREAM_BENCH_SAMPLE_RATE <= 0.0:
        return False
    return random.random() <= _STREAM_BENCH_SAMPLE_RATE


def _estimate_tokens_from_chars(char_count: int) -> int:
    if char_count <= 0:
        return 0
    # ざっくり推定（多言語混在向け）: 4文字 ≒ 1 token
    return max(1, round(char_count / 4))


def _extract_text_and_reasoning_chars_from_chunk(chunk: Any) -> tuple[int, int]:
    text_chars = 0
    reasoning_chars = 0

    if isinstance(chunk, str):
        return len(chunk), 0

    content = _normalize_content_parts_for_ui(_extract_chunk_content(chunk))
    if isinstance(content, str):
        return len(content), 0
    if not isinstance(content, list):
        return 0, 0

    for part in content:
        if isinstance(part, str):
            text_chars += len(part)
            continue
        if not isinstance(part, dict):
            continue

        part_type = part.get("type")
        if part_type in {"thinking", "reasoning"}:
            thinking = part.get("thinking")
            if isinstance(thinking, str):
                reasoning_chars += len(thinking)
                continue

        text_value = part.get("text")
        if not isinstance(text_value, str):
            continue

        if part_type in {"thinking", "reasoning"}:
            reasoning_chars += len(text_value)
        else:
            text_chars += len(text_value)

    return text_chars, reasoning_chars


def _read_content_part_field(part: Any, key: str) -> Any:
    if isinstance(part, dict):
        return part.get(key)
    return getattr(part, key, None)


def _normalize_content_parts_for_ui(content: Any) -> str | list[Any] | None:
    if isinstance(content, str):
        return content if content else None
    if not isinstance(content, list):
        return None

    normalized_parts: list[Any] = []
    for part in content:
        if isinstance(part, str):
            if part:
                normalized_parts.append(part)
            continue

        part_type = _read_content_part_field(part, "type")
        text = _read_content_part_field(part, "text")
        thinking = _read_content_part_field(part, "thinking")

        normalized: dict[str, Any] = {}
        if isinstance(part_type, str) and part_type:
            normalized["type"] = part_type
        if isinstance(text, str) and text:
            normalized["text"] = text
        if isinstance(thinking, str) and thinking:
            normalized["thinking"] = thinking

        if normalized:
            normalized_parts.append(normalized)

    return normalized_parts if normalized_parts else None


def _extract_chunk_content(chunk: Any) -> Any:
    if isinstance(chunk, dict):
        return chunk.get("content")
    return getattr(chunk, "content", None)


def _extract_chunk_position(chunk: Any) -> Any:
    if isinstance(chunk, dict):
        return chunk.get("chunk_position")
    return getattr(chunk, "chunk_position", None)


def _extract_chunk_additional_kwargs(chunk: Any) -> dict[str, Any]:
    if isinstance(chunk, dict):
        raw = chunk.get("additional_kwargs")
    else:
        raw = getattr(chunk, "additional_kwargs", None)
    return raw if isinstance(raw, dict) else {}


def _extract_reasoning_text_from_additional_kwargs(chunk: Any) -> str:
    additional_kwargs = _extract_chunk_additional_kwargs(chunk)
    reasoning_value = additional_kwargs.get("reasoning_content")
    if isinstance(reasoning_value, str):
        return reasoning_value
    if isinstance(reasoning_value, list):
        parts: list[str] = []
        for item in reasoning_value:
            if isinstance(item, str):
                parts.append(item)
                continue
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def _compact_chat_chunk(chunk: Any, *, content_override: Any | None = None) -> dict[str, Any] | None:
    content = _normalize_content_parts_for_ui(
        content_override if content_override is not None else _extract_chunk_content(chunk)
    )
    if content is None:
        return None

    compact: dict[str, Any] = {"content": content}
    chunk_position = _extract_chunk_position(chunk)
    if isinstance(chunk_position, str) and chunk_position:
        compact["chunk_position"] = chunk_position
    return compact


def _filter_planner_writer_content_for_ui(chunk: Any) -> Any | None:
    normalized_content = _normalize_content_parts_for_ui(_extract_chunk_content(chunk))

    filtered_parts: list[dict[str, Any]] = []
    if isinstance(normalized_content, list):
        for part in normalized_content:
            if not isinstance(part, dict):
                continue
            part_type = part.get("type")
            if part_type not in {"thinking", "reasoning"}:
                continue

            thinking = part.get("thinking")
            text = part.get("text")
            if isinstance(thinking, str) and thinking:
                filtered_parts.append({"type": "thinking", "thinking": thinking})
                continue
            if isinstance(text, str) and text:
                filtered_parts.append({"type": "thinking", "text": text})

    # Gemini may stream thoughts via additional_kwargs.reasoning_content instead of content parts.
    if not filtered_parts:
        reasoning_text = _extract_reasoning_text_from_additional_kwargs(chunk)
        if reasoning_text:
            filtered_parts.append({"type": "thinking", "thinking": reasoning_text})

    return filtered_parts if filtered_parts else None


def _is_supervisor_internal_run(*, node: str, run_name: str, checkpoint: str) -> bool:
    is_supervisor_node = node == "supervisor" or checkpoint.find("supervisor:") >= 0
    is_supervisor_user_facing = run_name == "supervisor"
    return (is_supervisor_node or run_name.startswith("supervisor_")) and not is_supervisor_user_facing


def _is_visual_or_analyst_run(*, node: str, checkpoint: str) -> bool:
    is_visualizer = node == "visualizer" or checkpoint.find("visualizer:") >= 0
    is_analyst = node == "data_analyst" or checkpoint.find("data_analyst:") >= 0
    return is_visualizer or is_analyst


def _is_researcher_internal_run(*, node: str, checkpoint: str) -> bool:
    is_researcher_subgraph = checkpoint.find("researcher:") >= 0
    return is_researcher_subgraph and node in {"manager", "research_worker"}


@app.post("/api/chat/stream_events")
async def custom_stream_events(request: Request, input_data: ChatRequest):
    """
    Custom implementation of stream_events to filter data sent to BFF.
    Only sends:
    - on_chat_model_stream (without citation_metadata)
    - on_custom_event (excluding citation_metadata)
    """
    try:
        request_start_ms = _now_ms()
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

        product_type = input_data.input.product_type

        await _ensure_thread_access(
            _manager.pool,
            thread_id=thread_id,
            uid=uid,
            create_if_missing=True,
            product_type=product_type,
        )
        
        # 2. Define Generator
        async def event_generator():
            benchmark_enabled = _should_collect_stream_bench()
            first_event_ms: float | None = None
            first_chat_token_ms: float | None = None
            total_events = 0
            total_chat_events = 0
            forwarded_chat_events = 0
            dropped_chat_events = 0
            total_custom_events = 0
            forwarded_custom_events = 0
            dropped_custom_events = 0
            total_text_chars = 0
            total_reasoning_chars = 0
            total_bytes_sent = 0
            setup_completed_ms: float | None = None

            try:
                # Use the 'input' field from the payload for the graph input
                # pydantic model 'input' field will contain ChatInput instance
                graph_input = input_data.input.model_dump()
                pptx_context = await _build_pptx_context(
                    attachments=graph_input.get("attachments") or [],
                    pptx_template_base64=graph_input.get("pptx_template_base64"),
                )
                if pptx_context is not None:
                    graph_input["pptx_context"] = pptx_context
                # Legacy compatibility input only; do not persist huge base64 payload in graph state.
                graph_input.pop("pptx_template_base64", None)
                
                # Merge request-level config (Thread ID) with payload config
                merged_config = input_data.config or {}
                merged_config.setdefault("configurable", {})
                merged_config["configurable"]["thread_id"] = thread_id
                merged_config["configurable"]["checkpoint_ns"] = uid
                merged_config["configurable"]["user_uid"] = uid
                merged_config.setdefault("recursion_limit", DEFAULT_RECURSION_LIMIT)
                setup_completed_ms = _now_ms()
                
                # Stream events from the graph
                async for event in graph_with_types.astream_events(
                    graph_input,
                    merged_config,
                    version="v2"
                ):
                    event_type = event.get("event")
                    now_ms = _now_ms()
                    if first_event_ms is None:
                        first_event_ms = now_ms
                    total_events += 1

                    # Filter Logic
                    if event_type == "on_chat_model_stream":
                        total_chat_events += 1
                        event_data = event.get("data") if isinstance(event.get("data"), dict) else {}
                        chunk = event_data.get("chunk")
                        if chunk is None:
                            dropped_chat_events += 1
                            continue

                        metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
                        run_name = str(metadata.get("run_name") or event.get("name") or "")
                        node = str(metadata.get("langgraph_node") or "")
                        checkpoint = str(
                            metadata.get("langgraph_checkpoint_ns")
                            or metadata.get("checkpoint_ns")
                            or ""
                        )

                        if _is_researcher_internal_run(node=node, checkpoint=checkpoint):
                            dropped_chat_events += 1
                            continue
                        if _is_visual_or_analyst_run(node=node, checkpoint=checkpoint):
                            dropped_chat_events += 1
                            continue
                        if _is_supervisor_internal_run(node=node, run_name=run_name, checkpoint=checkpoint):
                            dropped_chat_events += 1
                            continue

                        is_planner = run_name == "planner" or node == "planner" or checkpoint.find("planner:") >= 0
                        is_writer = run_name == "writer" or node == "writer" or checkpoint.find("writer:") >= 0
                        is_coordinator = run_name == "coordinator" or node == "coordinator" or checkpoint.find("coordinator:") >= 0
                        normalized_chunk: dict[str, Any] | None = None

                        if is_coordinator:
                            dropped_chat_events += 1
                            continue

                        if is_planner or is_writer:
                            planner_writer_content = _filter_planner_writer_content_for_ui(chunk)
                            if planner_writer_content is None:
                                dropped_chat_events += 1
                                continue
                            normalized_chunk = _compact_chat_chunk(chunk, content_override=planner_writer_content)
                        else:
                            normalized_chunk = _compact_chat_chunk(chunk)

                        if normalized_chunk is None:
                            dropped_chat_events += 1
                            continue

                        forwarded_chat_events += 1
                        text_chars, reasoning_chars = _extract_text_and_reasoning_chars_from_chunk(normalized_chunk)
                        total_text_chars += text_chars
                        total_reasoning_chars += reasoning_chars
                        if first_chat_token_ms is None and (text_chars > 0 or reasoning_chars > 0):
                            first_chat_token_ms = now_ms

                        payload: dict[str, Any] = {
                            "event": "on_chat_model_stream",
                            "data": {"chunk": normalized_chunk},
                        }
                        run_id = event.get("run_id")
                        if run_id is not None:
                            payload["run_id"] = run_id
                        name = event.get("name")
                        if isinstance(name, str) and name:
                            payload["name"] = name
                        compact_metadata = _compact_stream_metadata(metadata)
                        if compact_metadata:
                            payload["metadata"] = compact_metadata

                        sse_payload = _encode_sse_payload(payload)
                        total_bytes_sent += len(sse_payload.encode("utf-8"))
                        yield sse_payload

                    elif event_type == "on_custom_event":
                        total_custom_events += 1
                        event_name = event.get("name")
                        if not isinstance(event_name, str):
                            dropped_custom_events += 1
                            continue

                        # Exclude citation_metadata standalone event
                        if event_name == "citation_metadata":
                            dropped_custom_events += 1
                            continue
                        if _STREAM_UI_EVENT_FILTER_ENABLED:
                            if event_name.startswith("data-"):
                                if event_name not in _ALLOWED_DATA_CUSTOM_EVENTS:
                                    dropped_custom_events += 1
                                    continue
                            elif event_name not in _ALLOWED_LEGACY_CUSTOM_EVENTS:
                                dropped_custom_events += 1
                                continue

                        forwarded_custom_events += 1
                        payload = {
                            "event": "on_custom_event",
                            "name": event_name,
                            "data": event.get("data"),
                        }
                        metadata = _compact_stream_metadata(event.get("metadata"))
                        if metadata:
                            payload["metadata"] = metadata

                        sse_payload = _encode_sse_payload(payload)
                        total_bytes_sent += len(sse_payload.encode("utf-8"))
                        yield sse_payload

                    # All other events (on_chain_start, on_tool_start, etc.) are IGNORED
            except Exception as stream_err:
                logger.error(f"Error inside stream generator: {stream_err}")
                if is_rate_limited_error(stream_err):
                    payload = {
                        "event": "error",
                        "data": {
                            "kind": "rate_limit",
                            "message": "現在アクセスが集中しています。数秒後に再送してください。",
                            "retryable": True,
                            "retry_after_seconds": 8,
                        },
                    }
                else:
                    payload = {
                        "event": "error",
                        "data": {
                            "kind": "internal",
                            "message": str(stream_err),
                            "retryable": False,
                        },
                    }
                sse_payload = _encode_sse_payload(payload)
                total_bytes_sent += len(sse_payload.encode("utf-8"))
                yield sse_payload
            finally:
                if benchmark_enabled:
                    end_ms = _now_ms()
                    first_event_latency_ms = (
                        round(first_event_ms - request_start_ms, 2)
                        if first_event_ms is not None else None
                    )
                    first_chat_token_latency_ms = (
                        round(first_chat_token_ms - request_start_ms, 2)
                        if first_chat_token_ms is not None else None
                    )
                    setup_latency_ms = (
                        round(setup_completed_ms - request_start_ms, 2)
                        if setup_completed_ms is not None else None
                    )
                    generation_window_ms = (
                        round(end_ms - first_chat_token_ms, 2)
                        if first_chat_token_ms is not None else None
                    )
                    text_tokens_est = _estimate_tokens_from_chars(total_text_chars)
                    reasoning_tokens_est = _estimate_tokens_from_chars(total_reasoning_chars)
                    total_tokens_est = text_tokens_est + reasoning_tokens_est

                    tokens_per_sec = None
                    if first_chat_token_ms is not None:
                        elapsed_sec = max((end_ms - first_chat_token_ms) / 1000.0, 1e-6)
                        tokens_per_sec = round(total_tokens_est / elapsed_sec, 2)

                    logger.info(
                        "[STREAM_BENCH][backend] %s",
                        json.dumps(
                            {
                                "thread_id": thread_id,
                                "product_type": product_type,
                                "events_total": total_events,
                                "chat_events": total_chat_events,
                                "chat_events_forwarded": forwarded_chat_events,
                                "chat_events_dropped": dropped_chat_events,
                                "custom_events": total_custom_events,
                                "custom_events_forwarded": forwarded_custom_events,
                                "custom_events_dropped": dropped_custom_events,
                                "bytes_sent": total_bytes_sent,
                                "text_chars": total_text_chars,
                                "reasoning_chars": total_reasoning_chars,
                                "text_tokens_est": text_tokens_est,
                                "reasoning_tokens_est": reasoning_tokens_est,
                                "tokens_est_total": total_tokens_est,
                                "setup_ms": setup_latency_ms,
                                "first_event_ms": first_event_latency_ms,
                                "first_chat_token_ms": first_chat_token_latency_ms,
                                "generation_window_ms": generation_window_ms,
                                "total_stream_ms": round(end_ms - request_start_ms, 2),
                                "tokens_est_per_sec": tokens_per_sec,
                            },
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    )

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
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


@app.post("/api/files/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(..., description="Upload image or pptx files"),
    thread_id: str | None = Form(default=None),
):
    uid = getattr(request.state, "user_uid", None)
    if not isinstance(uid, str) or not uid:
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files. Maximum is {MAX_UPLOAD_FILES}")

    session_key = _normalize_session_key(thread_id, uid)
    uploaded_items: list[dict[str, Any]] = []

    for upload in files:
        original_name = upload.filename or "upload"
        safe_name = _sanitize_filename(original_name)
        display_name = _normalize_display_filename(original_name, fallback=safe_name)
        guessed_content_type = mimetypes.guess_type(safe_name)[0]
        content_type = (upload.content_type or guessed_content_type or "application/octet-stream").lower()
        payload = await upload.read()
        size_bytes = len(payload)
        if size_bytes <= 0:
            raise HTTPException(status_code=400, detail=f"Empty file: {display_name}")

        kind = _validate_upload_file(
            content_type=content_type,
            filename=safe_name,
            size_bytes=size_bytes,
        )

        object_name = f"user_uploads/{session_key}/{uuid.uuid4().hex}_{safe_name}"
        try:
            file_url = await asyncio.to_thread(
                upload_to_gcs,
                payload,
                content_type=content_type,
                object_name=object_name,
            )
        except Exception as storage_error:
            logger.error("Failed to upload file %s: %s", safe_name, storage_error)
            raise HTTPException(status_code=500, detail=f"Failed to store file: {safe_name}")
        finally:
            await upload.close()

        uploaded_items.append(
            {
                "id": uuid.uuid4().hex,
                "filename": display_name,
                "mime_type": content_type,
                "size_bytes": size_bytes,
                "url": file_url,
                "kind": kind,
            }
        )

    return {"attachments": uploaded_items}


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
    normalized = normalize_plan_v2(
        [dict(step) for step in plan if isinstance(step, dict)],
        product_type=None,
    )
    for index, row in enumerate(normalized, start=1):
        row.setdefault("id", index)
    return [jsonable_encoder(row) for row in normalized]


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


WRITER_ARTIFACT_META: dict[str, dict[str, str]] = {
    "outline": {"title": "Slide Outline", "mode": "slide_outline"},
    "writer_story_framework": {"title": "Story Framework", "mode": "story_framework"},
    "writer_character_sheet": {"title": "Character Sheet", "mode": "character_sheet"},
    "writer_infographic_spec": {"title": "Infographic Spec", "mode": "infographic_spec"},
    "writer_document_blueprint": {"title": "Document Blueprint", "mode": "document_blueprint"},
    "writer_comic_script": {"title": "Comic Script", "mode": "comic_script"},
}


def _infer_writer_status(data: dict[str, Any]) -> str:
    failed_checks = data.get("failed_checks")
    if isinstance(failed_checks, list) and len(failed_checks) > 0:
        return "failed"
    error_text = data.get("error")
    if isinstance(error_text, str) and error_text.strip():
        return "failed"
    summary = str(data.get("execution_summary") or "")
    lowered = summary.lower()
    if "error" in lowered or "失敗" in summary or "エラー" in summary:
        return "failed"
    return "completed"


def _build_writer_output_event(
    *,
    artifact_id: str,
    artifact_type: str,
    output: dict[str, Any],
) -> dict[str, Any]:
    meta = WRITER_ARTIFACT_META.get(artifact_type, {})
    return {
        "type": "data-writer-output",
        "data": {
            "artifact_id": artifact_id,
            "title": meta.get("title", "Writer Output"),
            "artifact_type": artifact_type,
            "mode": meta.get("mode", "unknown"),
            "output": output,
        },
    }


def _build_writer_structured_artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    normalized_data = jsonable_encoder(data)
    status = _infer_writer_status(data)
    meta = WRITER_ARTIFACT_META.get(artifact_type, {})

    artifact = {
        "id": artifact_id,
        "type": artifact_type,
        "title": meta.get("title", "Writer Output"),
        "content": normalized_data,
        "version": 1,
        "status": status,
    }
    return artifact, [
        _build_writer_output_event(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            output=normalized_data,
        )
    ]


def _is_visual_output_payload(data: dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False

    visual_keys = {
        "generated_image_url",
        "image_url",
        "compiled_prompt",
        "image_generation_prompt",
        "structured_prompt",
        "rationale",
        "layout_type",
        "selected_inputs",
    }

    def _rows_have_visual_keys(rows: Any) -> bool:
        if not isinstance(rows, list):
            return False
        for row in rows:
            if not isinstance(row, dict):
                continue
            if any(key in row for key in visual_keys):
                return True
        return False

    if _rows_have_visual_keys(data.get("prompts")):
        return True
    if _rows_have_visual_keys(data.get("slides")):
        return True
    if _rows_have_visual_keys(data.get("design_pages")):
        return True
    if _rows_have_visual_keys(data.get("comic_pages")):
        return True
    if _rows_have_visual_keys(data.get("pages")):
        return True
    if _rows_have_visual_keys(data.get("characters")):
        return True
    if isinstance(data.get("combined_pdf_url"), str):
        return True
    if isinstance(data.get("mode"), str) and isinstance(data.get("generation_config"), dict):
        return True
    return False


def _build_visual_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []

    mode = data.get("mode") if isinstance(data.get("mode"), str) else None
    product_type = data.get("product_type") if isinstance(data.get("product_type"), str) else None

    events: list[dict[str, Any]] = []
    slides: list[dict[str, Any]] = []

    units: dict[tuple[str, int], dict[str, Any]] = {}

    def _append_units(raw_rows: Any, *, unit_kind: str, number_key: str) -> None:
        if not isinstance(raw_rows, list):
            return
        for row in raw_rows:
            if not isinstance(row, dict):
                continue
            unit_number = row.get(number_key)
            if not isinstance(unit_number, int):
                fallback_number = row.get("slide_number")
                if isinstance(fallback_number, int):
                    unit_number = fallback_number
            if not isinstance(unit_number, int):
                continue
            units[(unit_kind, unit_number)] = row

    _append_units(data.get("prompts"), unit_kind="slide", number_key="slide_number")
    _append_units(data.get("slides"), unit_kind="slide", number_key="slide_number")
    _append_units(data.get("design_pages"), unit_kind="page", number_key="page_number")
    _append_units(data.get("comic_pages"), unit_kind="page", number_key="page_number")
    _append_units(data.get("pages"), unit_kind="page", number_key="page_number")  # legacy compatibility
    _append_units(data.get("characters"), unit_kind="character", number_key="character_number")

    for (unit_kind, unit_number), row in sorted(units.items(), key=lambda item: (item[0][1], item[0][0])):
        structured_prompt = row.get("structured_prompt")
        structured_title = (
            structured_prompt.get("main_title")
            if isinstance(structured_prompt, dict)
            else None
        )
        default_label = "Slide" if unit_kind == "slide" else "Page" if unit_kind == "page" else "Character"
        title = row.get("title") or structured_title or f"{default_label} {unit_number}"

        generated_image_url = row.get("generated_image_url")
        image_url = (
            generated_image_url
            if isinstance(generated_image_url, str) and generated_image_url.strip()
            else row.get("image_url")
        )
        prompt_text = row.get("compiled_prompt") or row.get("image_generation_prompt") or row.get("prompt_text")
        explicit_status = row.get("status")
        status = (
            explicit_status.strip()
            if isinstance(explicit_status, str) and explicit_status.strip()
            else ("completed" if isinstance(image_url, str) and image_url else "streaming")
        )

        slide: dict[str, Any] = {
            "slide_number": unit_number,
            "title": title,
            "unit_kind": unit_kind,
            "status": status,
        }
        if unit_kind == "page":
            slide["page_number"] = unit_number
        if unit_kind == "character":
            slide["character_number"] = unit_number
            if isinstance(row.get("character_name"), str):
                slide["character_name"] = row.get("character_name")
        if isinstance(image_url, str) and image_url:
            slide["image_url"] = image_url
        if isinstance(prompt_text, str) and prompt_text:
            slide["prompt_text"] = prompt_text
        if structured_prompt is not None:
            slide["structured_prompt"] = structured_prompt
        if row.get("rationale") is not None:
            slide["rationale"] = row.get("rationale")
        if row.get("layout_type") is not None:
            slide["layout_type"] = row.get("layout_type")
        if row.get("selected_inputs") is not None:
            slide["selected_inputs"] = row.get("selected_inputs")
        slides.append(slide)

        image_event_data: dict[str, Any] = {
            "artifact_id": artifact_id,
            "deck_title": "Generated Slides",
            "asset_unit_kind": unit_kind,
            "slide_number": unit_number,
            "page_number": unit_number if unit_kind == "page" else None,
            "character_number": unit_number if unit_kind == "character" else None,
            "title": title,
            "image_url": image_url,
            "prompt_text": prompt_text,
            "structured_prompt": structured_prompt,
            "rationale": row.get("rationale"),
            "layout_type": row.get("layout_type"),
            "selected_inputs": row.get("selected_inputs"),
            "status": status,
        }
        if isinstance(mode, str) and mode:
            image_event_data["mode"] = mode
        if isinstance(product_type, str) and product_type:
            image_event_data["product_type"] = product_type
        events.append({"type": "data-visual-image", "data": image_event_data})

    pdf_url = data.get("combined_pdf_url")
    if isinstance(pdf_url, str) and pdf_url:
        pdf_event_data: dict[str, Any] = {
            "artifact_id": artifact_id,
            "deck_title": "Generated Slides",
            "pdf_url": pdf_url,
            "status": "completed",
        }
        if isinstance(mode, str) and mode:
            pdf_event_data["mode"] = mode
        if isinstance(product_type, str) and product_type:
            pdf_event_data["product_type"] = product_type
        events.append({"type": "data-visual-pdf", "data": pdf_event_data})

    if not slides:
        return None, events

    is_completed = all(bool(slide.get("image_url")) for slide in slides)
    content_payload: dict[str, Any] = {
        "slides": slides,
        "pdf_url": pdf_url,
    }
    if isinstance(mode, str) and mode:
        content_payload["mode"] = mode
    if isinstance(product_type, str) and product_type:
        content_payload["product_type"] = product_type

    artifact = {
        "id": artifact_id,
        "type": "slide_deck",
        "title": "Generated Slides",
        "content": content_payload,
        "version": 1,
        "status": "completed" if is_completed else "streaming",
    }
    return artifact, events


def _build_story_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []
    status = _infer_writer_status(data)

    slides = data.get("slides")
    if isinstance(slides, list):
        normalized_slides = [jsonable_encoder(slide) for slide in slides if isinstance(slide, dict)]
        outline_event = {
            "type": "data-outline",
            "data": {
                "artifact_id": artifact_id,
                "slides": normalized_slides,
                "title": "Slide Outline",
            },
        }

        artifact = {
            "id": artifact_id,
            "type": "outline",
            "title": "Slide Outline",
            "content": _build_story_outline(normalized_slides),
            "version": 1,
            "status": status,
        }
        writer_event = _build_writer_output_event(
            artifact_id=artifact_id,
            artifact_type="outline",
            output=jsonable_encoder(data),
        )
        return artifact, [outline_event, writer_event]

    if isinstance(data.get("characters"), list):
        return _build_writer_structured_artifact(
            artifact_id=artifact_id,
            artifact_type="writer_character_sheet",
            data=data,
        )

    if isinstance(data.get("blocks"), list) and isinstance(data.get("key_message"), str):
        return _build_writer_structured_artifact(
            artifact_id=artifact_id,
            artifact_type="writer_infographic_spec",
            data=data,
        )

    story_framework_payload = data.get("story_framework")
    if (
        isinstance(story_framework_payload, dict)
        and isinstance(story_framework_payload.get("concept"), str)
        and isinstance(story_framework_payload.get("format_policy"), dict)
    ):
        return _build_writer_structured_artifact(
            artifact_id=artifact_id,
            artifact_type="writer_story_framework",
            data=data,
        )

    if isinstance(data.get("key_beats"), list) and isinstance(data.get("logline"), str):
        return _build_writer_structured_artifact(
            artifact_id=artifact_id,
            artifact_type="writer_story_framework",
            data=data,
        )

    pages = data.get("pages")
    if isinstance(pages, list):
        has_panels = any(isinstance(page, dict) and isinstance(page.get("panels"), list) for page in pages)
        has_sections = any(isinstance(page, dict) and isinstance(page.get("sections"), list) for page in pages)
        if has_panels or (isinstance(data.get("genre"), str) and isinstance(data.get("title"), str)):
            return _build_writer_structured_artifact(
                artifact_id=artifact_id,
                artifact_type="writer_comic_script",
                data=data,
            )
        if has_sections or isinstance(data.get("document_type"), str):
            return _build_writer_structured_artifact(
                artifact_id=artifact_id,
                artifact_type="writer_document_blueprint",
                data=data,
            )

    return None, []


def _build_data_analyst_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []

    if not any(key in data for key in ("implementation_code", "execution_log", "output_value")):
        return None, []

    failed_checks = data.get("failed_checks")
    has_failed_checks = isinstance(failed_checks, list) and len(failed_checks) > 0
    execution_log = str(data.get("execution_log") or "")
    lowered_log = execution_log.lower()
    is_failed = (
        has_failed_checks
        or "error" in lowered_log
        or "失敗" in execution_log
        or "エラー" in execution_log
    )
    status = "failed" if is_failed else "completed"
    implementation_code = str(data.get("implementation_code") or "")
    execution_log = str(data.get("execution_log") or "")
    raw_input = data.get("input")
    normalized_input = jsonable_encoder(raw_input) if isinstance(raw_input, dict) else None

    artifact = {
        "id": artifact_id,
        "type": "data_analyst",
        "title": "Data Analyst",
        "content": {
            "input": normalized_input,
            "code": implementation_code,
            "log": execution_log,
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
                "input": normalized_input,
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


def _build_research_artifact(artifact_id: str, value: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    data = _safe_json_loads(value)
    if not isinstance(data, dict):
        return None, []

    if "report" not in data and "perspective" not in data:
        return None, []

    perspective = str(data.get("perspective") or "Research")
    report = str(data.get("report") or "")
    artifact = {
        "id": artifact_id,
        "type": "report",
        "title": f"Research: {perspective}",
        "content": report or json.dumps(jsonable_encoder(data), ensure_ascii=False, indent=2),
        "version": 1,
        "status": "completed",
    }

    events: list[dict[str, Any]] = []
    events.append(
        {
            "type": "data-research-report",
            "data": {
                "artifact_id": artifact_id,
                "task_id": data.get("task_id"),
                "perspective": perspective,
                "search_mode": data.get("search_mode"),
                "status": "completed",
                "report": report,
                "sources": jsonable_encoder(data.get("sources") if isinstance(data.get("sources"), list) else []),
            },
        }
    )

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
    raw_followups = state_values.get("coordinator_followup_options")
    if isinstance(raw_followups, list):
        options: list[dict[str, str]] = []
        for index, option in enumerate(raw_followups, start=1):
            if not isinstance(option, dict):
                continue
            prompt = option.get("prompt")
            if not isinstance(prompt, str) or not prompt.strip():
                continue
            option_id = option.get("id")
            normalized_id = option_id if isinstance(option_id, str) and option_id.strip() else f"followup_{index}"
            options.append({"id": normalized_id, "prompt": prompt.strip()})
            if len(options) >= 3:
                break
        if options:
            ui_events.append(
                {
                    "type": "data-coordinator-followups",
                    "data": {
                        "options": options,
                    },
                }
            )

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
            elif suffix == "research":
                artifact, events = _build_research_artifact(artifact_id, value)
            elif suffix == "data":
                artifact, events = _build_data_analyst_artifact(artifact_id, value)
            else:
                parsed = _safe_json_loads(value)
                if isinstance(parsed, dict) and _is_visual_output_payload(parsed):
                    artifact, events = _build_visual_artifact(artifact_id, parsed)
                elif isinstance(parsed, dict) and "slides" in parsed:
                    artifact, events = _build_story_artifact(artifact_id, parsed)
                elif isinstance(parsed, dict) and (
                    "report" in parsed or "image_candidates" in parsed
                ):
                    artifact, events = _build_research_artifact(artifact_id, parsed)
                elif isinstance(parsed, dict) and (
                    "implementation_code" in parsed
                    or "execution_log" in parsed
                    or "output_value" in parsed
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
        "product_type": state_values.get("product_type"),
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
                        product_type,
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
                    product_type_val = row[3]
                    updated_at = row[4]
                    
                    history.append({
                        "id": thread_id,
                        "title": title or f"Session {thread_id[:8]}",
                        "product_type": product_type_val,
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
        try:
            state = await graph.aget_state(config)
        except Exception as e:
            # Handle incompatible checkpoints (e.g., after graph structure changes)
            if "Subgraph" in str(e) and "not found" in str(e):
                logger.warning(f"Checkpoint mismatch for thread {thread_id}: {e}. Returning empty state.")
                return {
                    "thread_id": thread_id,
                    "messages": [],
                    "plan": [],
                    "artifacts": {},
                    "ui_events": [],
                    "error": "Checkpoint incompatibility detected. Please start a new thread."
                }
            raise e

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


# === In-painting API ===

class InpaintReferenceImage(BaseModel):
    image_url: str = Field(..., min_length=1, description="Reference image URL for style/content guidance")
    caption: Optional[str] = Field(default=None, description="Optional note describing this reference")
    mime_type: Optional[str] = Field(default=None, description="Optional MIME type (e.g., image/png)")


class InpaintRequest(BaseModel):
    image_url: str = Field(..., description="Source image URL to edit")
    mask_image_url: str = Field(
        ...,
        description="Mask image URL or data URL (white=editable, black=preserve)",
    )
    prompt: str = Field(..., min_length=1, description="Modification instruction")
    reference_images: list[InpaintReferenceImage] = Field(
        default_factory=list,
        description="Optional reference images to guide style/content during in-painting",
    )


def _inpaint_source_kind(image_ref: str) -> str:
    source = (image_ref or "").strip().lower()
    if source.startswith("data:"):
        return "data_url"
    if source.startswith("gs://"):
        return "gcs_uri"
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        return f"{parsed.scheme}_url"
    return "unknown"


def _build_inpaint_instruction(
    user_prompt: str,
    reference_images: list[InpaintReferenceImage] | None = None,
) -> str:
    cleaned = user_prompt.strip()
    references = reference_images or []
    reference_mapping_lines = [
        "- Image[1] = ORIGINAL (source image)",
        "- Image[2] = MASK (white = editable, black = preserve)",
    ]
    if references:
        reference_mapping_lines.append(
            "- Image[3..N] = OPTIONAL REFERENCE IMAGES (style/content guidance only)"
        )
        for index, reference in enumerate(references, start=3):
            caption = (reference.caption or "").strip()
            suffix = f" ({caption})" if caption else ""
            reference_mapping_lines.append(f"- Image[{index}] = REFERENCE{suffix}")
    reference_mapping_text = "\n".join(reference_mapping_lines)
    return (
        "You are an image inpainting model.\n"
        "Reference mapping (strict order):\n"
        f"{reference_mapping_text}\n"
        "Never swap these roles.\n"
        "Apply edits only inside white masked regions.\n"
        "Outside the white mask, preserve composition, style, lighting, and all text exactly.\n\n"
        "Optional references are guidance only. Do not copy unrelated layout/content outside the mask.\n\n"
        f"Edit instruction:\n{cleaned}"
    )


def _normalize_inpaint_mime_type(mime_type: str | None) -> str | None:
    if not isinstance(mime_type, str):
        return None
    normalized = mime_type.strip().lower()
    if not normalized.startswith("image/"):
        return None
    return normalized


def _infer_inpaint_mime_type(image_ref: str, default: str = "image/png") -> str:
    source = (image_ref or "").strip()
    if not source:
        return default

    if source.lower().startswith("data:"):
        header = source.split(",", 1)[0]
        if ";" in header:
            media = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
            if media.startswith("image/"):
                return media
        return default

    parsed = urlparse(source)
    path = parsed.path if parsed.scheme in {"http", "https", "gs"} else source
    guessed, _ = mimetypes.guess_type(path)
    normalized = _normalize_inpaint_mime_type(guessed)
    return normalized or default


async def _resolve_inpaint_reference(image_ref: str, *, field_name: str) -> str | bytes:
    source = (image_ref or "").strip()
    if not source:
        raise ValueError(f"{field_name} is required")

    if source.startswith("data:"):
        decoded = _decode_base64_payload(source)
        if not decoded:
            raise ValueError(f"Invalid {field_name} data URL")
        return decoded

    if source.startswith("gs://"):
        return source

    payload = await asyncio.to_thread(download_blob_as_bytes, source)
    if not payload:
        raise ValueError(f"Failed to download {field_name}")
    return payload


async def _run_inpaint(
    image_url: str,
    mask_image_url: str,
    prompt: str,
    reference_images: list[InpaintReferenceImage] | None = None,
    session_id: str | None = None,
    slide_number: int | None = None,
) -> str:
    if not image_url:
        raise ValueError("image_url is required")
    if not mask_image_url:
        raise ValueError("mask_image_url is required")

    references = reference_images or []
    if len(references) > MAX_INPAINT_REFERENCE_IMAGES:
        raise ValueError(
            f"reference_images supports up to {MAX_INPAINT_REFERENCE_IMAGES} items"
        )

    source_input = await _resolve_inpaint_reference(image_url, field_name="image_url")
    mask_input = await _resolve_inpaint_reference(mask_image_url, field_name="mask_image_url")
    source_mime_type = _infer_inpaint_mime_type(source_input) if isinstance(source_input, str) else _infer_inpaint_mime_type(image_url)
    mask_mime_type = _infer_inpaint_mime_type(mask_input) if isinstance(mask_input, str) else _infer_inpaint_mime_type(mask_image_url)
    inpaint_reference_inputs: list[dict[str, Any]] = [
        (
            {"uri": source_input, "mime_type": source_mime_type}
            if isinstance(source_input, str)
            else {"data": source_input, "mime_type": source_mime_type}
        ),
        (
            {"uri": mask_input, "mime_type": mask_mime_type}
            if isinstance(mask_input, str)
            else {"data": mask_input, "mime_type": mask_mime_type}
        ),
    ]
    for index, reference in enumerate(references):
        resolved_reference = await _resolve_inpaint_reference(
            reference.image_url,
            field_name=f"reference_images[{index}].image_url",
        )
        reference_mime_type = (
            _normalize_inpaint_mime_type(reference.mime_type)
            or (
                _infer_inpaint_mime_type(resolved_reference)
                if isinstance(resolved_reference, str)
                else _infer_inpaint_mime_type(reference.image_url)
            )
        )
        inpaint_reference_inputs.append(
            (
                {"uri": resolved_reference, "mime_type": reference_mime_type}
                if isinstance(resolved_reference, str)
                else {"data": resolved_reference, "mime_type": reference_mime_type}
            )
        )

    inpaint_prompt = _build_inpaint_instruction(prompt, reference_images=references)

    image_bytes, _ = await asyncio.to_thread(
        generate_image,
        inpaint_prompt,
        seed=None,
        reference_image=inpaint_reference_inputs,
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
            mask_image_url=request.mask_image_url,
            prompt=request.prompt,
            reference_images=request.reference_images,
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
        logger.warning(
            "In-painting validation failed for image_id=%s (image_source=%s, mask_source=%s, references=%s): %s",
            image_id,
            _inpaint_source_kind(request.image_url),
            _inpaint_source_kind(request.mask_image_url),
            len(request.reference_images or []),
            ve,
        )
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(
            "In-painting failed for image_id=%s (image_source=%s, mask_source=%s, prompt_len=%s, references=%s, error_type=%s)",
            image_id,
            _inpaint_source_kind(request.image_url),
            _inpaint_source_kind(request.mask_image_url),
            len(request.prompt or ""),
            len(request.reference_images or []),
            type(e).__name__,
        )
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
            mask_image_url=request.mask_image_url,
            prompt=request.prompt,
            reference_images=request.reference_images,
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
        logger.warning(
            "In-painting validation failed for deck_id=%s slide_number=%s (image_source=%s, mask_source=%s, references=%s): %s",
            deck_id,
            slide_number,
            _inpaint_source_kind(request.image_url),
            _inpaint_source_kind(request.mask_image_url),
            len(request.reference_images or []),
            ve,
        )
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(
            "In-painting failed for deck_id=%s slide_number=%s (image_source=%s, mask_source=%s, prompt_len=%s, references=%s, error_type=%s)",
            deck_id,
            slide_number,
            _inpaint_source_kind(request.image_url),
            _inpaint_source_kind(request.mask_image_url),
            len(request.prompt or ""),
            len(request.reference_images or []),
            type(e).__name__,
        )
        raise HTTPException(status_code=500, detail="In-painting failed")
