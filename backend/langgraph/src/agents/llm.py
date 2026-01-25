"""
LLMファクトリモジュール

設定に基づいて適切なLangChain LLMインスタンスを生成する。
OpenAI, DeepSeek, Google Gemini (AI Studio / Vertex AI) に対応。
"""
from functools import lru_cache
from typing import Union
import logging
import os

from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from langchain_google_genai import ChatGoogleGenerativeAI

from src.config.settings import settings

logger = logging.getLogger(__name__)


def create_openai_llm(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0
) -> ChatOpenAI:
    """OpenAI互換のLLMインスタンスを生成する。"""
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )


def create_deepseek_llm(
    model: str,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0
) -> ChatDeepSeek:
    """DeepSeekのLLMインスタンスを生成する。"""
    return ChatDeepSeek(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
    )


def create_gemini_llm(
    model: str,
    api_key: str | None = None,
    project: str | None = None,
    location: str | None = None,
    temperature: float = 0.0
) -> ChatGoogleGenerativeAI:
    """
    ChatGoogleGenerativeAI インスタンスを生成する。

    AI Studio (API Key) と Vertex AI (ADC/Project) の両方に対応。
    google-genai SDK が内部で認証を処理する。

    Args:
        model: モデル名
        api_key: Google AI Studio の API キー（Vertex AI 使用時は None）
        project: Vertex AI プロジェクトID
        location: Vertex AI ロケーション
        temperature: 生成温度

    Returns:
        ChatGoogleGenerativeAI インスタンス
    """
    # Vertex AI 設定（環境変数経由で google-genai に渡す）
    # NOTE: langchain-google-genai は環境変数を参照するため、ここで設定する
    if project:
        os.environ["GOOGLE_CLOUD_PROJECT"] = project
        os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "true"
    if location:
        os.environ["GOOGLE_CLOUD_LOCATION"] = location

    kwargs: dict = {
        "model": model,
        "temperature": temperature,
    }

    # API Key モード（AI Studio）の場合のみ google_api_key を設定
    # Vertex AI モードでは環境変数経由で認証されるため不要
    if api_key:
        kwargs["google_api_key"] = api_key

    return ChatGoogleGenerativeAI(**kwargs)


@lru_cache(maxsize=10)
def get_llm_by_type(llm_type: str) -> Union[ChatOpenAI, ChatDeepSeek, ChatGoogleGenerativeAI]:
    """
    設定に基づいてLLMインスタンスを取得するファクトリ関数。

    キャッシュにより同一タイプのLLMは再利用される。

    Args:
        llm_type: LLMタイプ ("reasoning", "vision", "high_reasoning", "basic")

    Returns:
        LLMインスタンス

    Raises:
        ValueError: 指定されたタイプのモデルが設定されていない場合
    """
    # 設定から対応するモデル情報を取得
    if llm_type == "reasoning":
        model = settings.REASONING_MODEL
        base_url = settings.REASONING_BASE_URL
        api_key = settings.REASONING_API_KEY
    elif llm_type == "vision":
        model = settings.VL_MODEL
        base_url = settings.VL_BASE_URL
        api_key = settings.VL_API_KEY
    elif llm_type == "high_reasoning":
        model = settings.HIGH_REASONING_MODEL
        base_url = settings.HIGH_REASONING_BASE_URL
        api_key = settings.HIGH_REASONING_API_KEY
    else:  # basic / default
        model = settings.BASIC_MODEL
        base_url = settings.BASIC_BASE_URL
        api_key = settings.BASIC_API_KEY

    if not model:
        raise ValueError(f"No model configured for type '{llm_type}'")

    model_lower = model.lower()

    # モデル名に基づいてプロバイダを判定
    if "gpt" in model_lower:
        return create_openai_llm(model, base_url, api_key)

    if "deepseek" in model_lower:
        return create_deepseek_llm(model, base_url, api_key)

    if "gemini" in model_lower:
        logger.info(
            f"DEBUG: Checking Auth for {llm_type}. "
            f"ProjectID: {'SET' if settings.VERTEX_PROJECT_ID else 'None'}, "
            f"APIKey: {'SET' if api_key else 'None'}"
        )

        # Vertex AI を優先（Project ID が設定されている場合）
        if settings.VERTEX_PROJECT_ID:
            logger.info(f"Using Vertex AI via ChatGoogleGenerativeAI for {llm_type} (model: {model})")
            return create_gemini_llm(
                model=model,
                api_key=None,  # ADC / Vertex Mode
                project=settings.VERTEX_PROJECT_ID,
                location=settings.VERTEX_LOCATION or "asia-northeast1",
                temperature=0.0
            )

        # API Key フォールバック（AI Studio）
        if api_key:
            logger.info(f"Using Google GenAI (API Key) for {llm_type} (model: {model})")
            return create_gemini_llm(model=model, api_key=api_key)

    # デフォルト: OpenAI互換
    return create_openai_llm(model, base_url, api_key)


# よく使われるLLMインスタンスを事前初期化
reasoning_llm = get_llm_by_type("reasoning")
basic_llm = get_llm_by_type("basic")
vl_llm = get_llm_by_type("vision")
