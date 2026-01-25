"""
設定モジュールの公開インターフェース

settings インスタンスと、後方互換のための設定値エイリアスを提供する。
"""
from .settings import settings
from .tools import GOOGLE_SEARCH_MAX_RESULTS

# Team configuration
TEAM_MEMBERS = ["storywriter", "researcher", "visualizer", "data_analyst"]

# ===========================
# 後方互換性のためのエイリアス
# 新規コードでは settings.XXX を直接使用することを推奨
# ===========================

# Reasoning LLM
REASONING_MODEL = settings.REASONING_MODEL
REASONING_BASE_URL = settings.REASONING_BASE_URL
REASONING_API_KEY = settings.REASONING_API_KEY

# Basic LLM
BASIC_MODEL = settings.BASIC_MODEL
BASIC_BASE_URL = settings.BASIC_BASE_URL
BASIC_API_KEY = settings.BASIC_API_KEY

# Vision-language LLM
VL_MODEL = settings.VL_MODEL
VL_BASE_URL = settings.VL_BASE_URL
VL_API_KEY = settings.VL_API_KEY

# Vertex AI
VERTEX_PROJECT_ID = settings.VERTEX_PROJECT_ID
VERTEX_LOCATION = settings.VERTEX_LOCATION

# External Services
CHROME_INSTANCE_PATH = settings.CHROME_INSTANCE_PATH

__all__ = [
    # メインの設定オブジェクト
    "settings",
    # Team config
    "TEAM_MEMBERS",
    "GOOGLE_SEARCH_MAX_RESULTS",
    # LLM エイリアス
    "REASONING_MODEL",
    "REASONING_BASE_URL",
    "REASONING_API_KEY",
    "BASIC_MODEL",
    "BASIC_BASE_URL",
    "BASIC_API_KEY",
    "VL_MODEL",
    "VL_BASE_URL",
    "VL_API_KEY",
    # Vertex AI
    "VERTEX_PROJECT_ID",
    "VERTEX_LOCATION",
    # External
    "CHROME_INSTANCE_PATH",
]
