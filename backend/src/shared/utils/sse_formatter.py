import json
from typing import Any


class DataStreamFormatter:
    """Format SSE data payloads for the frontend protocol."""

    def _sse(self, payload: dict[str, Any]) -> str:
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    def text_start(self, message_id: str) -> str:
        return self._sse({"type": "text-start", "id": message_id})

    def text_delta(self, message_id: str, delta: str) -> str:
        return self._sse({"type": "text-delta", "id": message_id, "delta": delta})

    def text_end(self, message_id: str) -> str:
        return self._sse({"type": "text-end", "id": message_id})

    def reasoning_start(self, message_id: str) -> str:
        return self._sse({"type": "reasoning-start", "id": message_id})

    def reasoning_delta(self, message_id: str, delta: str) -> str:
        return self._sse({"type": "reasoning-delta", "id": message_id, "delta": delta})

    def reasoning_end(self, message_id: str) -> str:
        return self._sse({"type": "reasoning-end", "id": message_id})

    def step_start(self, step_id: str) -> str:
        return self._sse({"type": "start-step", "id": step_id})

    def step_finish(self, step_id: str) -> str:
        return self._sse({"type": "finish-step", "id": step_id})

    def data_part(self, part_type: str, content: Any) -> str:
        return self._sse({"type": part_type, "content": content})

    def file_part(self, url: str, media_type: str) -> str:
        return self._sse({"type": "file", "url": url, "mediaType": media_type})

    def tool_call(self, tool_call_id: str, tool_name: str, input_payload: Any) -> str:
        return self._sse(
            {
                "type": "tool-input-available",
                "toolCallId": tool_call_id,
                "toolName": tool_name,
                "input": input_payload,
            }
        )

    def tool_result(self, tool_call_id: str, output: Any) -> str:
        return self._sse(
            {"type": "tool-output-available", "toolCallId": tool_call_id, "output": output}
        )
