"""
アプリケーション設定

環境変数から設定値を読み込み、一元管理するためのPydantic Settingsモジュール。
すべての設定はこのファイルで定義し、他のモジュールからは `settings` インスタンス経由で参照する。
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    アプリケーション設定クラス。

    環境変数または.envファイルから値を読み込む。
    例: MAX_RETRIES=5 を .env に記述すると上書きされる。
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # ===========================
    # LLM Model Configuration
    # ===========================

    # Reasoning LLM (複雑な推論タスク用)
    REASONING_MODEL: str = Field(default="gemini-2.0-flash-thinking-exp-1219")
    REASONING_BASE_URL: str | None = Field(default=None)
    REASONING_API_KEY: str | None = Field(default=None)

    # Basic LLM (シンプルなタスク用)
    BASIC_MODEL: str = Field(default="gemini-1.5-flash-002")
    BASIC_BASE_URL: str | None = Field(default=None)
    BASIC_API_KEY: str | None = Field(default=None)

    # Vision LLM (画像理解タスク用)
    VL_MODEL: str = Field(default="gemini-3-pro-image-preview")
    VL_BASE_URL: str | None = Field(default=None)
    VL_API_KEY: str | None = Field(default=None)

    # High Reasoning LLM (高度な推論タスク用)
    HIGH_REASONING_MODEL: str = Field(default="gemini-2.0-flash-thinking-exp-1219")
    HIGH_REASONING_BASE_URL: str | None = Field(default=None)
    HIGH_REASONING_API_KEY: str | None = Field(default=None)

    # ===========================
    # Vertex AI Configuration
    # ===========================
    VERTEX_PROJECT_ID: str | None = Field(default=None)
    VERTEX_LOCATION: str | None = Field(default=None)

    # ===========================
    # External Services
    # ===========================
    CHROME_INSTANCE_PATH: str | None = Field(default=None)
    JINA_API_KEY: str | None = Field(default=None)

    # ===========================
    # Utils Configuration
    # ===========================
    PPTX_RENDER_TIMEOUT: int = Field(default=60)

    # ===========================
    # Storage & Persistence
    # ===========================
    GCS_BUCKET_NAME: str | None = Field(default=None)
    POSTGRES_DB_URI: str | None = Field(default=None)

    # ===========================
    # Retry & Concurrency Limits
    # ===========================
    MAX_RETRIES: int = Field(default=3)
    VISUALIZER_CONCURRENCY: int = Field(default=5)
    RESEARCHER_CONCURRENCY: int = Field(default=3)

    # ===========================
    # Recursion Limits
    # ===========================
    RECURSION_LIMIT_WORKFLOW: int = Field(default=50)
    RECURSION_LIMIT_RESEARCHER: int = Field(default=7)

    # ===========================
    # Service Limits
    # ===========================
    MAX_COORD_CACHE_SIZE: int = Field(default=2)

    # ===========================
    # Project Info
    # ===========================
    PROJECT_NAME: str = Field(default="Spell")
    VERSION: str = Field(default="0.1.0")
    DEBUG: bool = Field(default=False)

    # ===========================
    # Response Template
    # ===========================
    RESPONSE_FORMAT: str = Field(
        default="Response from {role}:\n\n<response>\n{content}\n</response>\n\n*Step completed.*"
    )


# アプリケーション全体で使用するシングルトンインスタンス
settings = Settings()
