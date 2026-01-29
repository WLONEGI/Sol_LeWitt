"""
ツールデコレータモジュール

LangChainツール関数に入出力ロギングを追加するデコレータを提供。
"""
import logging
import functools
from typing import Any, Callable

logger = logging.getLogger(__name__)


def log_io(func: Callable) -> Callable:
    """
    ツール関数の入力パラメータと出力をログに記録するデコレータ。

    Args:
        func: デコレート対象のツール関数

    Returns:
        入出力ロギング付きのラップされた関数
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 入力パラメータをログ出力
        func_name = func.__name__
        params = ", ".join(
            [*(str(arg) for arg in args), *(f"{k}={v}" for k, v in kwargs.items())]
        )
        logger.debug(f"Tool {func_name} called with parameters: {params}")

        # 関数を実行
        result = func(*args, **kwargs)

        # 出力をログ出力
        logger.debug(f"Tool {func_name} returned: {result}")

        return result

    return wrapper
