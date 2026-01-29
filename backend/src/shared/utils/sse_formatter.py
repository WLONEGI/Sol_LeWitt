"""
Data Stream Protocol Formatter for Vercel AI SDK (JSON SSE)

Outputs streaming responses in the Data Stream Protocol format (JSON SSE):
- data: {"type": "type_name", ...}

Reference: https://sdk.vercel.ai/docs/ai-sdk-ui/stream-protocol
"""

import json
from typing import Any, Optional


class DataStreamFormatter:
    """
    Formatter for Vercel AI SDK Data Stream Protocol (JSON SSE v1).
    Enforces 'data: {...}' format for all messages.
    """

    def _emit_event(self, event_data: dict) -> str:
        """
        Emit a Server-Sent Event with JSON data.
        Format: data: {json_payload}\n\n
        """
        return f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"

    # --- Text Parts ---

    def text_start(self, msg_id: str) -> str:
        """
        Text Start Part
        Indicates the beginning of a text block.
        """
        return self._emit_event({"type": "text-start", "id": msg_id})

    def text_delta(self, msg_id: str, content: str) -> str:
        """
        Text Delta Part
        Contains incremental text content.
        """
        return self._emit_event({"type": "text-delta", "id": msg_id, "delta": content})

    def text_end(self, msg_id: str) -> str:
        """
        Text End Part
        Indicates the completion of a text block.
        """
        return self._emit_event({"type": "text-end", "id": msg_id})

    def text(self, text_delta: str) -> str:
        """
        Legacy/Simple text emitter. 
        WARNING: This does not support ID tracking required by JSON protocol.
        Ideally should be avoided in favor of text_delta(id, content).
        """
        # Fallback to a static ID if used, or just log warning?
        # For now, we assume this usage is migrated or we use a temporary ID.
        return self.text_delta("legacy_text_id", text_delta)

    # --- Reasoning Parts ---

    def reasoning_start(self, rs_id: str) -> str:
        """
        Reasoning Start Part
        Indicates the beginning of a reasoning block.
        """
        return self._emit_event({"type": "reasoning-start", "id": rs_id})

    def reasoning_delta(self, rs_id: str, content: str) -> str:
        """
        Reasoning Delta Part
        Contains incremental reasoning content.
        """
        return self._emit_event({"type": "reasoning-delta", "id": rs_id, "delta": content})

    def reasoning_end(self, rs_id: str) -> str:
        """
        Reasoning End Part
        Indicates the completion of a reasoning block.
        """
        return self._emit_event({"type": "reasoning-end", "id": rs_id})

    def reasoning(self, delta: str, metadata: dict = {}) -> str:
        """
        Helper for reasoning chunks if ID is provided in metadata.
        """
        rs_id = metadata.get("id", "legacy_reasoning_id")
        return self.reasoning_delta(rs_id, delta)

    # --- Data Parts (Custom Events) ---
    
    def data_part(self, type_str: str, data: Any) -> str:
        """
        Generic Data Part for custom events.
        Compliant with Vercel AI SDK Data Stream Protocol.
        Emits a JSON object: {"type": "data-...", "data": ...}
        """
        return self._emit_event({
            "type": type_str,
            "data": data
        })

    def data(self, data_list: list[dict[str, Any]]) -> str:
        """
        Emit a batch of custom data items.
        """
        if not data_list:
            return ""
        
        # Emit each item independently as Vercel AI SDK expects stream parts
        events = ""
        for item in data_list:
             events += self._emit_event(item)
        return events

    # --- Tool Parts ---

    def tool_call(self, tool_call_id: str, tool_name: str, args: dict) -> str:
        """
        Tool Input Available Part (Call)
        Indicates that tool input is complete and ready for execution (or start/delta pattern).
        Here we emit 'tool-input-available' as we usually have full call info in backend.
        """
        return self._emit_event({
            "type": "tool-input-available",
            "toolCallId": tool_call_id,
            "toolName": tool_name,
            "input": args
        })

    def tool_result(self, tool_call_id: str, result: Any) -> str:
        """
        Tool Output Available Part (Result)
        Contains the result of tool execution.
        """
        return self._emit_event({
            "type": "tool-output-available",
            "toolCallId": tool_call_id,
            "output": result
        })

    # --- Source / File Parts ---

    def file_part(self, url: str, mime_type: str) -> str:
        """
        File Part
        References to files with their media type.
        """
        return self._emit_event({
            "type": "file",
            "url": url,
            "mediaType": mime_type
        })

    def source_url(self, source_id: str, url: str) -> str:
        """
        Source URL Part
        References to external URLs.
        """
        return self._emit_event({
            "type": "source-url",
            "sourceId": source_id,
            "url": url
        })

    # --- Lifecycle Parts ---

    def step_start(self, step_id: str) -> str:
        """Start Step Part."""
        return self._emit_event({"type": "start-step"})

    def step_finish(self, step_id: str) -> str:
        """Finish Step Part."""
        return self._emit_event({"type": "finish-step"})

    def finish(self) -> str:
        """Finish Message Part."""
        return self._emit_event({"type": "finish"})

    def error(self, message: str) -> str:
        """Error Part."""
        return self._emit_event({"type": "error", "errorText": message})

    def done(self) -> str:
        """Stream Termination."""
        # Note: The docs mentions [DONE] literal for termination in some contexts,
        # but modern AI SDK stream-protocol often stops at connection close.
        # However, `text/event-stream` standard often doesn't need it if connection closes.
        # We'll emit nothing or a specific 'finish' event which we did above.
        return "" 


def create_sse_headers() -> dict:
    """
    Return HTTP headers for Data Stream Protocol responses.
    """
    return {
        "Content-Type": "text/event-stream", # Standard SSE
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
        "x-vercel-ai-ui-message-stream": "v1",
        "X-Accel-Buffering": "no",
    }
