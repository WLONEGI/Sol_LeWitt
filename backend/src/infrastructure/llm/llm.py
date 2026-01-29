"""
LLMファクトリモジュール

設定に基づいて適切なLLMインスタンスを生成する。
Google Vertex AI に対応。
"""
from functools import lru_cache
import logging
import os

from langchain_google_vertexai import ChatVertexAI

from src.shared.config.settings import settings

logger = logging.getLogger(__name__)


def create_gemini_llm(
    model: str,
    project: str | None = None,
    location: str | None = None,
    temperature: float = 0.0
) -> ChatVertexAI:
    """
    Gemini LLM インスタンス (Vertex AI) を生成する。

    Args:
        model: モデル名
        project: Vertex AI プロジェクトID
        location: Vertex AI ロケーション
        temperature: 生成温度

    Returns:
        ChatVertexAI インスタンス
    """
    # Vertex AI モード (必須)
    if not project:
         # 設定ファイル等から取得できていない場合は警告を出すが、実行環境(ADC)によっては動作する可能性があるためNoneも許容する設計とする
         # ただし、Vertex AI利用時はProject IDの明示が推奨される。
         if settings.VERTEX_PROJECT_ID:
             project = settings.VERTEX_PROJECT_ID
         else:
             logger.warning("Vertex AI Project ID is not set. Relying on default environment configuration.")

    logger.info(f"Creating ChatVertexAI for project={project}, location={location}")
    
    from langchain_google_vertexai import HarmCategory, HarmBlockThreshold
    
    # Safety settings to reduce empty responses (recitation/safety blocks)
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }

    return ChatVertexAI(
        model=model,
        project=project,
        location=location,
        temperature=temperature,
        max_retries=settings.MAX_RETRIES,
        # streaming=True, # Removed to see if it fixes the hang
        safety_settings=safety_settings,
    )


@lru_cache(maxsize=10)
def get_llm_by_type(llm_type: str) -> ChatVertexAI:
    """
    設定に基づいてLLMインスタンスを取得するファクトリ関数。

    キャッシュにより同一タイプのLLMは再利用される。

    Args:
        llm_type: LLMタイプ ("reasoning", "vision", "high_reasoning", "basic")

    Returns:
        LLMインスタンス (ChatVertexAI)

    Raises:
        ValueError: 指定されたタイプのモデルが設定されていない場合
    """
    # 設定から対応するモデル情報を取得
    if llm_type == "reasoning":
        model = settings.REASONING_MODEL
    elif llm_type == "vision":
        model = settings.VL_MODEL
    elif llm_type == "high_reasoning":
        model = settings.HIGH_REASONING_MODEL
    else:  # basic / default
        model = settings.BASIC_MODEL

    if not model:
        raise ValueError(f"No model configured for type '{llm_type}'")

    logger.info(
        f"DEBUG: Checking Auth for {llm_type}. "
        f"ProjectID: {'SET' if settings.VERTEX_PROJECT_ID else 'None'}"
    )

    # Vertex AI を利用
    logger.info(f"Using Vertex AI via ChatVertexAI for {llm_type} (model: {model})")
    return create_gemini_llm(
        model=model,
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION or "asia-northeast1",
        temperature=0.0
    )


# よく使われるLLMインスタンスを事前初期化

