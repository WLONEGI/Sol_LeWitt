"""
test_jina_client.py

src/crawler/jina_client.py のユニットテスト。
HTTP通信のモック化により、外部依存なしでテスト可能。
"""
import pytest
from unittest.mock import patch, MagicMock
import httpx


class TestJinaClientCrawl:
    """JinaClient.crawl メソッドのテスト"""

    @patch("httpx.post")
    def test_正常系_HTMLフォーマットで取得(self, mock_post: MagicMock):
        """HTMLフォーマットでコンテンツを取得できることを確認"""
        from src.crawler.jina_client import JinaClient

        # モックレスポンス設定
        mock_response = MagicMock()
        mock_response.text = "<html><body>Test Content</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = JinaClient()
        result = client.crawl("https://example.com", return_format="html")

        # 結果確認
        assert result == "<html><body>Test Content</body></html>"
        
        # httpx.post が正しく呼ばれたことを確認
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["url"] == "https://example.com"
        assert "X-Return-Format" in call_args.kwargs["headers"]
        assert call_args.kwargs["headers"]["X-Return-Format"] == "html"

    @patch("httpx.post")
    def test_正常系_Markdownフォーマットで取得(self, mock_post: MagicMock):
        """Markdownフォーマットでコンテンツを取得できることを確認"""
        from src.crawler.jina_client import JinaClient

        mock_response = MagicMock()
        mock_response.text = "# Title\n\nContent here"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = JinaClient()
        result = client.crawl("https://example.com", return_format="markdown")

        assert result == "# Title\n\nContent here"
        assert mock_post.call_args.kwargs["headers"]["X-Return-Format"] == "markdown"

    @patch("httpx.post")
    def test_正常系_APIキーありの場合Authorizationヘッダー追加(self, mock_post: MagicMock):
        """APIキーが設定されている場合、Authorizationヘッダーが追加されることを確認"""
        from src.crawler.jina_client import JinaClient

        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        # settings をモック
        with patch("src.crawler.jina_client.settings") as mock_settings:
            mock_settings.JINA_API_KEY = "test_api_key_12345"

            client = JinaClient()
            client.crawl("https://example.com")

            # Authorizationヘッダーが設定されていることを確認
            headers = mock_post.call_args.kwargs["headers"]
            assert "Authorization" in headers
            assert headers["Authorization"] == "Bearer test_api_key_12345"

    @patch("httpx.post")
    def test_正常系_APIキーなしの場合警告ログ出力(self, mock_post: MagicMock):
        """APIキーが未設定の場合、警告ログが出力されることを確認"""
        from src.crawler.jina_client import JinaClient

        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        with patch("src.crawler.jina_client.settings") as mock_settings:
            mock_settings.JINA_API_KEY = None

            with patch("src.crawler.jina_client.logger") as mock_logger:
                client = JinaClient()
                client.crawl("https://example.com")

                # 警告ログが出力されたことを確認
                mock_logger.warning.assert_called()
                warning_message = mock_logger.warning.call_args[0][0]
                assert "Jina API key is not set" in warning_message

    @patch("httpx.post")
    def test_異常系_HTTPエラー(self, mock_post: MagicMock):
        """HTTPエラー時にhttpx.HTTPStatusErrorが発生することを確認"""
        from src.crawler.jina_client import JinaClient

        # HTTPエラーをシミュレート
        mock_response = MagicMock()
        mock_request = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "404 Not Found", request=mock_request, response=mock_response
        )
        mock_post.return_value = mock_response

        client = JinaClient()
        
        with pytest.raises(httpx.HTTPStatusError):
            client.crawl("https://nonexistent.example.com")

    @patch("httpx.post")
    def test_異常系_接続エラー(self, mock_post: MagicMock):
        """接続エラー時に例外が発生することを確認"""
        from src.crawler.jina_client import JinaClient

        # 接続エラーをシミュレート
        mock_post.side_effect = httpx.ConnectError("Connection refused")

        client = JinaClient()
        
        with pytest.raises(httpx.ConnectError):
            client.crawl("https://example.com")

    @patch("httpx.post")
    def test_異常系_タイムアウト(self, mock_post: MagicMock):
        """タイムアウト時に例外が発生することを確認"""
        from src.crawler.jina_client import JinaClient

        # タイムアウトをシミュレート
        mock_post.side_effect = httpx.TimeoutException("Request timed out")

        client = JinaClient()
        
        with pytest.raises(httpx.TimeoutException):
            client.crawl("https://example.com")

    @patch("httpx.post")
    def test_境界値_空のレスポンス(self, mock_post: MagicMock):
        """空のレスポンスが返された場合"""
        from src.crawler.jina_client import JinaClient

        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = JinaClient()
        result = client.crawl("https://example.com")

        # 空文字が返ること
        assert result == ""

    @patch("httpx.post")
    def test_正常系_タイムアウト設定が渡される(self, mock_post: MagicMock):
        """リクエストにタイムアウトが設定されていることを確認"""
        from src.crawler.jina_client import JinaClient

        mock_response = MagicMock()
        mock_response.text = "content"
        mock_response.raise_for_status = MagicMock()
        mock_post.return_value = mock_response

        client = JinaClient()
        client.crawl("https://example.com")

        # タイムアウトが設定されていることを確認
        assert mock_post.call_args.kwargs.get("timeout") is not None
        assert mock_post.call_args.kwargs["timeout"] == 30
