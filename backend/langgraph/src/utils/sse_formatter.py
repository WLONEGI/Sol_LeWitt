"""
AI SDK v6 UI Message Stream Protocol のSSEフォーマッター

Vercel AI SDK v6の新しいUI Message Streamプロトコルに準拠した
Server-Sent Events (SSE) 形式でイベントを生成するユーティリティ。

プロトコル仕様:
- ヘッダー: x-vercel-ai-ui-message-stream: v1
- Content-Type: text/event-stream
- 形式: data: {JSON}\n\n
"""

import json
import uuid
from typing import Any, Optional


class UIMessageStreamFormatter:
    """
    AI SDK v6 UI Message Stream Protocol 形式でSSEを生成するフォーマッター
    
    ライフサイクル:
    1. start_message() - メッセージ開始
    2. text_start() - テキストブロック開始
    3. text_delta() - テキスト差分（複数回）
    4. text_end() - テキストブロック終了
    5. finish() - 完了 + [DONE]
    
    拡張イベント:
    - reasoning_start/delta/end - 推論プロセス
    - tool_call / tool_result - ツール呼び出し
    - custom_data - カスタムデータ (data-* タイプ)
    - error - エラー
    """
    
    def __init__(self, message_id: Optional[str] = None):
        """
        Args:
            message_id: メッセージID（省略時は自動生成）
        """
        self.message_id = message_id or f"msg-{uuid.uuid4().hex[:12]}"
        self._text_id_counter = 0
        self._reasoning_id_counter = 0
        self._current_text_id: Optional[str] = None
        self._current_reasoning_id: Optional[str] = None
        self._text_started = False
        self._reasoning_started = False
    
    @staticmethod
    def _sse(data: dict) -> str:
        """SSE形式でデータを出力"""
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    
    # --- メッセージライフサイクル ---
    
    def start_message(self) -> str:
        """メッセージ開始イベント"""
        return self._sse({
            "type": "start",
            "messageId": self.message_id
        })
    
    def finish(self, finish_reason: str = "stop") -> str:
        """
        完了イベント + [DONE]
        
        Args:
            finish_reason: 完了理由 (stop, length, error など)
        """
        # 開いているブロックを閉じる
        events = ""
        if self._text_started:
            events += self.text_end()
        if self._reasoning_started:
            events += self.reasoning_end()
        
        events += self._sse({
            "type": "finish",
            "finishReason": finish_reason
        })
        events += "data: [DONE]\n\n"
        return events
    
    # --- テキストストリーミング ---
    
    def text_start(self) -> str:
        """テキストブロック開始"""
        self._text_id_counter += 1
        self._current_text_id = f"txt-{self._text_id_counter}"
        self._text_started = True
        return self._sse({
            "type": "text-start",
            "id": self._current_text_id
        })
    
    def text_delta(self, delta: str, auto_start: bool = True) -> str:
        """
        テキスト差分
        
        Args:
            delta: テキストの差分
            auto_start: テキストブロックが開始していない場合、自動で開始するか
        """
        events = ""
        if auto_start and not self._text_started:
            events += self.text_start()
        
        events += self._sse({
            "type": "text-delta",
            "id": self._current_text_id,
            "delta": delta
        })
        return events
    
    def text_end(self) -> str:
        """テキストブロック終了"""
        if not self._text_started:
            return ""
        self._text_started = False
        return self._sse({
            "type": "text-end",
            "id": self._current_text_id
        })
    
    # --- 推論 (Reasoning) ストリーミング ---
    
    def reasoning_start(self) -> str:
        """推論ブロック開始"""
        self._reasoning_id_counter += 1
        self._current_reasoning_id = f"rsn-{self._reasoning_id_counter}"
        self._reasoning_started = True
        return self._sse({
            "type": "reasoning-start",
            "id": self._current_reasoning_id
        })
    
    def reasoning_delta(self, delta: str, auto_start: bool = True) -> str:
        """
        推論差分
        
        Args:
            delta: 推論テキストの差分
            auto_start: 推論ブロックが開始していない場合、自動で開始するか
        """
        events = ""
        if auto_start and not self._reasoning_started:
            events += self.reasoning_start()
        
        events += self._sse({
            "type": "reasoning-delta",
            "id": self._current_reasoning_id,
            "delta": delta
        })
        return events
    
    def reasoning_end(self) -> str:
        """推論ブロック終了"""
        if not self._reasoning_started:
            return ""
        self._reasoning_started = False
        return self._sse({
            "type": "reasoning-end",
            "id": self._current_reasoning_id
        })
    
    # --- ツール呼び出し ---
    
    def tool_call(
        self, 
        tool_call_id: str, 
        tool_name: str, 
        args: dict
    ) -> str:
        """
        ツール呼び出しイベント
        
        Args:
            tool_call_id: ツール呼び出しID
            tool_name: ツール名
            args: ツール引数
        """
        return self._sse({
            "type": "tool-call",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "args": args
        })
    
    def tool_result(
        self, 
        tool_call_id: str, 
        tool_name: str,
        result: Any
    ) -> str:
        """
        ツール実行結果イベント
        
        Args:
            tool_call_id: ツール呼び出しID
            tool_name: ツール名
            result: 実行結果
        """
        return self._sse({
            "type": "tool-result",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "result": result
        })
    
    # --- カスタムデータ ---
    
    def custom_data(
        self, 
        data_type: str, 
        data: dict, 
        data_id: Optional[str] = None,
        transient: bool = False
    ) -> str:
        """
        カスタムデータイベント (data-* タイプ)
        
        Args:
            data_type: データタイプ（例: "progress", "artifact", "workflow"）
                      自動的に "data-" プレフィックスが付与される
            data: データペイロード
            data_id: データID（省略時は自動生成）
            transient: True の場合、メッセージ履歴に保存されない
        """
        event_data = {
            "type": f"data-{data_type}",
            "id": data_id or f"{data_type}-{uuid.uuid4().hex[:8]}",
            "data": data
        }
        if transient:
            event_data["transient"] = True
        return self._sse(event_data)
    
    # --- エラー ---
    
    def error(self, error_message: str, code: Optional[str] = None) -> str:
        """
        エラーイベント
        
        Args:
            error_message: エラーメッセージ
            code: エラーコード（省略可）
        """
        event_data = {
            "type": "error",
            "error": error_message
        }
        if code:
            event_data["code"] = code
        return self._sse(event_data)
    
    # --- ソース/引用 ---
    
    def source_url(
        self,
        source_id: str,
        url: str,
        title: Optional[str] = None
    ) -> str:
        """
        ソースURL（引用元）イベント
        
        Args:
            source_id: ソースID
            url: URL
            title: タイトル（省略可）
        """
        value = {
            "type": "source",
            "id": source_id,
            "url": url
        }
        if title:
            value["title"] = title
        
        return self._sse({
            "type": "source-url",
            "value": value
        })


# 便利な関数
def create_sse_headers() -> dict:
    """UI Message Stream 用のHTTPヘッダーを返す"""
    return {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "x-vercel-ai-ui-message-stream": "v1",
    }
