"""
Data Stream Protocol Formatter for Vercel AI SDK

Outputs streaming responses in the Data Stream Protocol format:
- 0:"text" - Text content
- d:{JSON} - Data part (custom data like progress, artifacts)
- e:{JSON} - Error
- 9:{JSON} - Tool call
- a:{JSON} - Tool result

Reference: https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol
"""

import json
from typing import Any, Optional


class DataStreamFormatter:
    """
    Formatter for Vercel AI SDK Data Stream Protocol.
    
    This protocol uses line-based prefix format for streaming:
    - 0: for text chunks
    - d: for data parts
    - e: for errors
    - 9: for tool calls
    - a: for tool results
    """
    
    @staticmethod
    def _escape_text(text: str) -> str:
        """Escape text for JSON string output."""
        return json.dumps(text, ensure_ascii=False)
    
    @staticmethod
    def _format_json(data: Any) -> str:
        """Format data as JSON."""
        return json.dumps(data, ensure_ascii=False)
    
    # --- Text Streaming ---
    
    def text(self, content: str) -> str:
        """
        Text chunk (prefix: 0:)
        
        Args:
            content: The text content to stream
            
        Returns:
            Formatted line: 0:"text content"\n
        """
        return f"0:{self._escape_text(content)}\n"
    
    # --- Data Parts ---
    
    def data(
        self, 
        data: dict | list,
        data_type: Optional[str] = None
    ) -> str:
        """
        Data part for custom data (prefix: d:)
        
        Args:
            data: The data payload (dict or list)
            data_type: Optional type to include in the payload
            
        Returns:
            Formatted line: d:{JSON}\n
            
        Note: LangGraph progress, artifacts, agent status etc.
        should be sent via this method.
        """
        if data_type and isinstance(data, dict):
            payload = {"type": data_type, **data}
        else:
            payload = data
        return f"d:{self._format_json(payload)}\n"
    
    # --- Error ---
    
    def error(self, message: str, code: Optional[str] = None) -> str:
        """
        Error event (prefix: e:)
        
        Args:
            message: Error message
            code: Optional error code
            
        Returns:
            Formatted line: e:{JSON}\n
        """
        payload: dict[str, Any] = {"error": message}
        if code:
            payload["code"] = code
        return f"e:{self._format_json(payload)}\n"
    
    # --- Tool Calls ---
    
    def tool_call(
        self,
        tool_call_id: str,
        tool_name: str,
        args: dict
    ) -> str:
        """
        Tool call event (prefix: 9:)
        
        Args:
            tool_call_id: Unique identifier for the tool call
            tool_name: Name of the tool being called
            args: Arguments passed to the tool
            
        Returns:
            Formatted line: 9:{JSON}\n
        """
        payload = {
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "args": args
        }
        return f"9:{self._format_json(payload)}\n"
    
    def tool_result(
        self,
        tool_call_id: str,
        result: Any
    ) -> str:
        """
        Tool result event (prefix: a:)
        
        Args:
            tool_call_id: The ID of the tool call this result is for
            result: The result from the tool execution
            
        Returns:
            Formatted line: a:{JSON}\n
        """
        payload = {
            "toolCallId": tool_call_id,
            "result": result
        }
        return f"a:{self._format_json(payload)}\n"
    
    # --- Lifecycle ---
    
    def finish(self, finish_reason: str = "stop") -> str:
        """
        Finish event - signals end of stream.
        
        Args:
            finish_reason: Reason for finishing (stop, length, error, etc.)
            
        Returns:
            Formatted data part with finish information
        """
        return self.data({"finishReason": finish_reason}, data_type="finish")


def create_sse_headers() -> dict:
    """
    Return HTTP headers for Data Stream Protocol responses.
    
    Returns:
        Headers dict with:
        - Content-Type: text/plain; charset=utf-8
        - X-Vercel-AI-Data-Stream: v1
    """
    return {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Vercel-AI-Data-Stream": "v1",
    }
