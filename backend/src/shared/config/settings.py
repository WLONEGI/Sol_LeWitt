"""
アプリケーション設定

環境変数から設定値を読み込み、一元管理するためのPydantic Settingsモジュール。
すべての設定はこのファイルで定義し、他のモジュールからは `settings` インスタンス経由で参照する。
"""
from pydantic import AliasChoices, Field
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
    REASONING_MODEL: str | None = Field(default=None)

    # Basic LLM (シンプルなタスク用)
    BASIC_MODEL: str | None = Field(default=None)

    # Vision LLM (画像理解タスク用)
    VL_MODEL: str | None = Field(default=None)

    # High Reasoning LLM (高度な推論タスク用)
    HIGH_REASONING_MODEL: str | None = Field(default=None)

    # ===========================
    # Vertex AI Configuration
    # ===========================
    VERTEX_PROJECT_ID: str | None = Field(default=None)
    VERTEX_LOCATION: str | None = Field(default=None)

    # ===========================
    # AI Studio Configuration
    # ===========================
    AI_STUDIO_API_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AI_STUDIO_API_KEY", "AI_STUDIO"),
    )

    # ===========================
    # External Services
    # ===========================
    CHROME_INSTANCE_PATH: str | None = Field(default=None)
    JINA_API_KEY: str | None = Field(default=None)
    FIREBASE_PROJECT_ID: str | None = Field(default=None)
    FIREBASE_SERVICE_ACCOUNT_JSON: str | None = Field(default=None)

    # ===========================
    # Utils Configuration
    # ===========================
    GOOGLE_SEARCH_MAX_RESULTS: int | None = Field(default=None)
    PPTX_RENDER_TIMEOUT: int | None = Field(default=None)

    # ===========================
    # Storage & Persistence
    # ===========================
    POSTGRES_DB_URI: str | None = Field(default=None)
    GCS_BUCKET_NAME: str | None = Field(default=None)
    
    # ===========================
    # Cloud SQL Configuration
    # ===========================
    CLOUD_SQL_CONNECTION_NAME: str | None = Field(default=None)

    # ===========================
    # Retry & Concurrency Limits
    # ===========================
    MAX_RETRIES: int | None = Field(default=None)
    VISUALIZER_CONCURRENCY: int | None = Field(default=None)
    RESEARCHER_CONCURRENCY: int | None = Field(default=None)

    # ===========================
    # Recursion Limits
    # ===========================
    RECURSION_LIMIT_WORKFLOW: int | None = Field(default=None)
    RECURSION_LIMIT_RESEARCHER: int | None = Field(default=None)

    # ===========================
    # Service Limits
    # ===========================
    MAX_COORD_CACHE_SIZE: int | None = Field(default=None)

    # ===========================
    # Project Info
    # ===========================
    PROJECT_NAME: str | None = Field(default=None)
    VERSION: str | None = Field(default=None)
    DEBUG: bool | None = Field(default=None)

    # ===========================
    # Response Template
    # ===========================
    RESPONSE_FORMAT: str | None = Field(default=None)

    @property
    def connection_string(self) -> str:
        """
        Get the database connection string, automatically adjusting for Cloud Run.
        
        Logic:
        1. Replace 'postgresql+psycopg://' with 'postgresql://' for asyncpg/psycopg.
        2. If running in Cloud Run (K_SERVICE is set) AND CLOUD_SQL_CONNECTION_NAME is set:
           - Force usage of Unix Domain Socket at /cloudsql/{CONNECTION_NAME}
        """
        if not self.POSTGRES_DB_URI:
            return ""

        uri = self.POSTGRES_DB_URI.replace("postgresql+psycopg://", "postgresql://")

        import os
        # Detect Cloud Run environment
        if os.environ.get("K_SERVICE") and self.CLOUD_SQL_CONNECTION_NAME:
            # Parse the existing URI to preserve user/pass/db
            # Format: postgresql://user:pass@host:port/dbname
            # Target: postgresql://user:pass@/dbname?host=/cloudsql/INSTANCE
            try:
                from urllib.parse import urlparse, quote_plus
                parsed = urlparse(uri)
                
                # Reconstruct without host/port, adding socket host
                # netloc contains user:pass@host:port
                user_pass = ""
                if "@" in parsed.netloc:
                    user_pass = parsed.netloc.split("@")[0] + "@"
                
                # Path is /dbname
                dbname = parsed.path
                
                socket_path = f"/cloudsql/{self.CLOUD_SQL_CONNECTION_NAME}"
                new_uri = f"postgresql://{user_pass}/{dbname.lstrip('/')}?host={socket_path}"
                return new_uri
            except Exception:
                # Fallback to original if parsing fails
                return uri
                
        return uri


# アプリケーション全体で使用するシングルトンインスタンス
settings = Settings()
