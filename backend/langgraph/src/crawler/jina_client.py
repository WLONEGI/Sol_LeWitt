"""
Jina Reader API クライアント

Webページのコンテンツを取得するためのクライアント。
"""
import logging
from typing import Literal

import httpx

from src.config.settings import settings

logger = logging.getLogger(__name__)


class JinaClient:
    """
    Jina Reader API を使用してWebページをクロールするクライアント。

    API キーは settings.JINA_API_KEY から取得される。
    API キーが未設定の場合はレート制限付きで動作する。
    """

    def crawl(
        self,
        url: str,
        return_format: Literal["html", "markdown", "text"] = "html"
    ) -> str:
        """
        指定されたURLのコンテンツを取得する。

        Args:
            url: 取得対象のURL
            return_format: 返却フォーマット ("html", "markdown", "text")

        Returns:
            取得したコンテンツ（文字列）

        Raises:
            httpx.HTTPStatusError: HTTPリクエストに失敗した場合
        """
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "X-Return-Format": return_format,
        }

        if settings.JINA_API_KEY:
            headers["Authorization"] = f"Bearer {settings.JINA_API_KEY}"
        else:
            logger.warning(
                "Jina API key is not set. Provide your own key to access a higher rate limit. "
                "See https://jina.ai/reader for more information."
            )

        data: dict[str, str] = {"url": url}
        response = httpx.post(
            "https://r.jina.ai/",
            headers=headers,
            json=data,
            timeout=30
        )
        response.raise_for_status()

        return response.text
