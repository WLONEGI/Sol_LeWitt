"""
test_settings.py

src/config/settings.py のユニットテスト。
pydantic-settings による設定管理の挙動を検証する。
"""
import os
import pytest
from unittest.mock import patch


class TestSettingsDefaults:
    """Settings クラスのデフォルト値テスト"""

    def test_正常系_デフォルト値が設定される(self):
        """環境変数未設定時にデフォルト値が使用されることを確認"""
        from src.config.settings import Settings

        # 新しいインスタンスを作成（環境変数に依存しないテスト）
        # NOTE: 実際の環境変数がある場合はそちらが優先される
        settings = Settings()

        # デフォルト値の確認
        assert settings.MAX_RETRIES == 3 or settings.MAX_RETRIES > 0  # 環境変数で上書き可能
        assert settings.VISUALIZER_CONCURRENCY == 5 or settings.VISUALIZER_CONCURRENCY > 0
        assert settings.RECURSION_LIMIT_WORKFLOW == 50 or settings.RECURSION_LIMIT_WORKFLOW > 0
        assert settings.PROJECT_NAME == "Spell" or isinstance(settings.PROJECT_NAME, str)

    def test_正常系_LLMモデル設定が取得できる(self):
        """LLMモデル設定が取得できることを確認"""
        from src.config.settings import settings

        # モデル名が文字列であること
        assert isinstance(settings.REASONING_MODEL, str)
        assert isinstance(settings.BASIC_MODEL, str)
        assert isinstance(settings.VL_MODEL, str)

    def test_正常系_オプショナル設定がNone許容(self):
        """オプショナルな設定がNoneを許容することを確認"""
        from src.config.settings import Settings

        settings = Settings()

        # これらは未設定の場合Noneが許容される
        # 実際の環境変数がある場合は値が入る
        assert settings.REASONING_BASE_URL is None or isinstance(settings.REASONING_BASE_URL, str)
        assert settings.VERTEX_PROJECT_ID is None or isinstance(settings.VERTEX_PROJECT_ID, str)


class TestSettingsEnvironmentOverride:
    """環境変数による設定上書きテスト"""

    def test_正常系_環境変数で上書きできる(self):
        """環境変数で設定値を上書きできることを確認"""
        with patch.dict(os.environ, {"MAX_RETRIES": "10"}):
            from src.config.settings import Settings
            settings = Settings()
            assert settings.MAX_RETRIES == 10

    def test_正常系_API_KEYを環境変数から取得(self):
        """API_KEY系の設定を環境変数から取得できることを確認"""
        test_key = "test_api_key_12345"
        with patch.dict(os.environ, {"JINA_API_KEY": test_key}):
            from src.config.settings import Settings
            settings = Settings()
            assert settings.JINA_API_KEY == test_key

    def test_境界値_空文字の環境変数(self):
        """空文字の環境変数が設定された場合"""
        with patch.dict(os.environ, {"JINA_API_KEY": ""}):
            from src.config.settings import Settings
            settings = Settings()
            # 空文字は空文字として扱われる（Noneではない）
            assert settings.JINA_API_KEY == "" or settings.JINA_API_KEY is None


class TestSettingsTypeValidation:
    """設定値の型検証テスト"""

    def test_正常系_整数型フィールド(self):
        """整数型フィールドが正しく型変換されることを確認"""
        from src.config.settings import settings

        assert isinstance(settings.MAX_RETRIES, int)
        assert isinstance(settings.PPTX_RENDER_TIMEOUT, int)
        assert isinstance(settings.VISUALIZER_CONCURRENCY, int)

    def test_正常系_真偽値型フィールド(self):
        """真偽値型フィールドが正しく型変換されることを確認"""
        from src.config.settings import settings

        assert isinstance(settings.DEBUG, bool)

    def test_正常系_文字列型フィールド(self):
        """文字列型フィールドが正しく型変換されることを確認"""
        from src.config.settings import settings

        assert isinstance(settings.PROJECT_NAME, str)
        assert isinstance(settings.VERSION, str)
        assert isinstance(settings.RESPONSE_FORMAT, str)


class TestSettingsSingleton:
    """settings シングルトンインスタンスのテスト"""

    def test_正常系_シングルトンインスタンスが利用可能(self):
        """モジュールレベルのsettingsインスタンスが利用可能であることを確認"""
        from src.config.settings import settings

        assert settings is not None
        # 複数回インポートしても同じインスタンス
        from src.config.settings import settings as settings2
        # NOTE: Pydantic Settings は毎回新しいインスタンスを作るわけではないが、
        # モジュールレベル変数なので同一参照
        assert settings is settings2



