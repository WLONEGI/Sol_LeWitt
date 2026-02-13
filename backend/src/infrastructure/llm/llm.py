"""
LLMファクトリモジュール

設定に基づいて適切なLLMインスタンスを生成する。
Google Vertex AI に対応（ChatVertexAI経由）。
"""
from functools import lru_cache
import logging
import asyncio
import random
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TypeVar

from langchain_google_genai import ChatGoogleGenerativeAI

from src.shared.config.settings import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")

RETRY_BASE_DELAY_SECONDS = 1.0
RETRY_MAX_DELAY_SECONDS = 8.0
RETRY_JITTER_SECONDS = 0.6
DEFAULT_MAX_RETRIES = 2
MAX_RETRY_CAP = 6


def _effective_max_retries() -> int:
    configured = settings.MAX_RETRIES
    if isinstance(configured, int):
        return max(0, min(configured, MAX_RETRY_CAP))
    return DEFAULT_MAX_RETRIES


def is_rate_limited_error(error: Exception) -> bool:
    status_code = getattr(error, "status_code", None)
    if status_code == 429:
        return True
    text = str(error).lower()
    return (
        "429" in text
        or "resource_exhausted" in text
        or "too many requests" in text
        or "rate limit" in text
    )


def _retry_delay_seconds(attempt: int) -> float:
    backoff = min(RETRY_MAX_DELAY_SECONDS, RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)))
    return backoff + random.uniform(0.0, RETRY_JITTER_SECONDS)


async def ainvoke_with_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    operation_name: str,
    max_retries: int | None = None,
) -> T:
    retries = _effective_max_retries() if max_retries is None else max(0, min(max_retries, MAX_RETRY_CAP))
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return await operation()
        except Exception as exc:
            if not is_rate_limited_error(exc) or attempt >= attempts:
                raise
            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "Rate limited on %s (attempt %s/%s). Retrying in %.2fs.",
                operation_name,
                attempt,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)
    raise RuntimeError(f"Unexpected retry state for {operation_name}")


async def astream_with_retry(
    stream_factory: Callable[[], AsyncIterator[T]],
    *,
    operation_name: str,
    max_retries: int | None = None,
) -> AsyncIterator[T]:
    retries = _effective_max_retries() if max_retries is None else max(0, min(max_retries, MAX_RETRY_CAP))
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        emitted_any = False
        try:
            async for chunk in stream_factory():
                emitted_any = True
                yield chunk
            return
        except Exception as exc:
            # If some tokens already streamed, do not retry to avoid duplicate content.
            if emitted_any or not is_rate_limited_error(exc) or attempt >= attempts:
                raise
            delay = _retry_delay_seconds(attempt)
            logger.warning(
                "Rate limited on %s before first chunk (attempt %s/%s). Retrying in %.2fs.",
                operation_name,
                attempt,
                attempts,
                delay,
            )
            await asyncio.sleep(delay)


def create_gemini_llm(
    model: str,
    project: str | None = None,
    location: str | None = None,
    temperature: float = 0.0,
    include_thoughts: bool = False,
    thinking_level: str | None = None,
    streaming: bool = True
) -> ChatGoogleGenerativeAI:
    """
    Gemini LLM インスタンス (Vertex AI経由) を生成する。

    ChatGoogleGenerativeAI は vertexai=True を設定することで Vertex AI バックエンドを使用。

    Args:
        model: モデル名
        project: Vertex AI プロジェクトID
        location: Vertex AI ロケーション
        temperature: 生成温度
        include_thoughts: 思考プロセスを含めるかどうか
        thinking_level: 思考レベル ("high", "medium", "low")
        streaming: ストリーミング有効化

    Returns:
        ChatGoogleGenerativeAI インスタンス
    """
    if not project:
        if settings.VERTEX_PROJECT_ID:
            project = settings.VERTEX_PROJECT_ID
        else:
            logger.warning("Vertex AI Project ID is not set. Relying on default environment configuration.")

    if not location:
        location = settings.VERTEX_LOCATION or "global"

    logger.info(
        f"Creating ChatGoogleGenerativeAI (Vertex AI mode) for project={project}, location={location}, "
        f"model={model}, include_thoughts={include_thoughts}, "
        f"thinking_level={thinking_level}, streaming={streaming}"
    )
    
    from langchain_google_genai import HarmCategory, HarmBlockThreshold
    
    # Safety settings
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }

    return ChatGoogleGenerativeAI(
        model=model,
        vertexai=True,
        project=project,
        location=location,
        temperature=temperature,
        max_retries=settings.MAX_RETRIES,
        # ChatGoogleGenerativeAI handles streaming automatically in astream
        streaming=streaming,
        safety_settings=safety_settings,
        include_thoughts=include_thoughts,
        thinking_level=thinking_level
    )


def create_grounded_llm(
    model: str | None = None,
    project: str | None = None,
    location: str | None = None,
    temperature: float = 0.0,
    streaming: bool = True,
) -> ChatGoogleGenerativeAI:
    """
    Google Search Grounding を有効化したLLMを作成する。
    
    常にGoogle検索を実行する静的(Static)モードでLLMインスタンスを返す。
    vertexai=True モードで動作し、bind(tools=[]) により検索機能を追加する。
    
    Args:
        model: モデル名（未指定時はREASONING_MODELを使用）
        project: Vertex AI プロジェクトID
        location: Vertex AI ロケーション
        temperature: 生成温度
    
    Returns:
        Google Search Grounding が有効化された ChatGoogleGenerativeAI インスタンス
    """
    # デフォルトモデルの設定
    if not model:
        model = settings.REASONING_MODEL
    
    if not project:
        project = settings.VERTEX_PROJECT_ID
    
    if not location:
        location = settings.VERTEX_LOCATION or "global"
    
    # Grounded LLM use the reasoning model by default, so we usually want thinking enabled here if it's the reasoning model
    include_thoughts = (model == settings.REASONING_MODEL or model == settings.HIGH_REASONING_MODEL)
    thinking_level = "low" if include_thoughts else None

    logger.info(
        f"Creating Grounded LLM (Google Search: Static) for project={project}, "
        f"location={location}, model={model}, include_thoughts={include_thoughts}, "
        f"thinking_level={thinking_level}"
    )
    
    # 1. Google検索ツールの定義 (Gemini API仕様準拠: 常に検索)
    google_search_tool = {
        "google_search": {}
    }
    
    # 2. LLMの初期化 (vertexai=True が必須)
    llm = create_gemini_llm(
        model=model,
        project=project,
        location=location,
        temperature=temperature,
        include_thoughts=include_thoughts,
        thinking_level=thinking_level,
        streaming=streaming,
    )
    
    # 3. ツールとしてバインド
    llm_with_search = llm.bind(tools=[google_search_tool])
    
    logger.info(f"Google Search Grounding (Static) has been enabled (include_thoughts={include_thoughts})")
    return llm_with_search


@lru_cache(maxsize=10)
def get_llm_by_type(llm_type: str, streaming: bool = True) -> ChatGoogleGenerativeAI:
    """
    設定に基づいてLLMインスタンスを取得するファクトリ関数。

    キャッシュにより同一タイプのLLMは再利用される。

    Args:
        llm_type: LLMタイプ ("reasoning", "vision", "high_reasoning", "basic")
        streaming: ストリーミングを有効にするかどうか (デフォルト: True)

    Returns:
        LLMインスタンス (ChatGoogleGenerativeAI)

    Raises:
        ValueError: 指定されたタイプのモデルが設定されていない場合
    """
    # 設定から対応するモデル情報を取得
    include_thoughts = False
    thinking_level = None

    if llm_type == "grounded":
        return create_grounded_llm(
            model=settings.REASONING_MODEL,
            project=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_LOCATION,
            temperature=0.0,
            streaming=streaming,
        )
    if llm_type == "reasoning":
        model = settings.REASONING_MODEL
        include_thoughts = True
        thinking_level = "low"
    elif llm_type == "vision":
        model = settings.VL_MODEL
    elif llm_type == "high_reasoning":
        model = settings.HIGH_REASONING_MODEL
        include_thoughts = True
        thinking_level = "low"
    else:  # basic / default
        model = settings.BASIC_MODEL
        include_thoughts = False

    if not model:
        raise ValueError(f"No model configured for type '{llm_type}'")

    logger.info(
        f"DEBUG: Checking Auth for {llm_type}. "
        f"ProjectID: {'SET' if settings.VERTEX_PROJECT_ID else 'None'}"
    )

    # Vertex AI を利用 (ChatVertexAI)
    logger.info(
        f"[DEBUG] Factory get_llm_by_type: '{llm_type}' "
        f"(streaming={streaming}, include_thoughts={include_thoughts})"
    )
    return create_gemini_llm(
        model=model,
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION,
        temperature=0.0,
        include_thoughts=include_thoughts,
        thinking_level=thinking_level,
        streaming=streaming
    )
