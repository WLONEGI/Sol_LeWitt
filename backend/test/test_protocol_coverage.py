
import unittest
import json
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), "../src"))

from shared.utils.sse_formatter import DataStreamFormatter

class TestDataStreamProtocol(unittest.TestCase):
    def setUp(self):
        self.fmt = DataStreamFormatter()

    def assertSSE(self, result, expected_type, content_check=None):
        """Helper to verify JSON SSE format: 'data: {json_payload}\n\n'"""
        self.assertTrue(result.startswith("data: "))
        self.assertTrue(result.endswith("\n\n"))
        
        json_str = result[6:].strip()
        payload = json.loads(json_str)
        
        self.assertEqual(payload.get("type"), expected_type)
        
        if content_check:
            if isinstance(content_check, dict):
                for k, v in content_check.items():
                    self.assertEqual(payload.get(k), v)
            elif callable(content_check):
                content_check(payload)
            else:
                # If specific checking logic is needed
                pass

    def test_text_stream(self):
        # Text Start
        self.assertSSE(self.fmt.text_start("msg_123"), "text-start", {"id": "msg_123"})
        
        # Text Delta
        self.assertSSE(self.fmt.text_delta("msg_123", "Hello"), "text-delta", {"id": "msg_123", "delta": "Hello"})
        
        # Text End
        self.assertSSE(self.fmt.text_end("msg_123"), "text-end", {"id": "msg_123"})

    def test_reasoning_stream(self):
        # Reasoning Start
        self.assertSSE(self.fmt.reasoning_start("rs_123"), "reasoning-start", {"id": "rs_123"})
        
        # Reasoning Delta
        self.assertSSE(self.fmt.reasoning_delta("rs_123", "Thinking..."), "reasoning-delta", {"id": "rs_123", "delta": "Thinking..."})
        
        # Reasoning End
        self.assertSSE(self.fmt.reasoning_end("rs_123"), "reasoning-end", {"id": "rs_123"})

    def test_agent_lifecycle(self):
        # Step Start
        self.assertSSE(self.fmt.step_start("step_1"), "start-step")
        
        # Agent Start (Core Data Part)
        data = {"id": "step_1", "agent_name": "researcher"}
        self.assertSSE(self.fmt.data_part("data-agent-start", data), "data-agent-start", 
                       {"content": data})

        # Step Finish
        self.assertSSE(self.fmt.step_finish("step_1"), "finish-step")

    def test_files(self):
        # Image file
        url = "http://example.com/img.png"
        self.assertSSE(self.fmt.file_part(url, "image/png"), "file",
                       {"url": url, "mediaType": "image/png"})

    def test_tool_execution(self):
        # Tool call
        self.assertSSE(self.fmt.tool_call("call_1", "search", {"q": "foo"}), "tool-input-available",
                       {"toolCallId": "call_1", "toolName": "search", "input": {"q": "foo"}})
        
        # Tool result
        self.assertSSE(self.fmt.tool_result("call_1", "result_abc"), "tool-output-available",
                       {"toolCallId": "call_1", "output": "result_abc"})

    def test_custom_data_wrapping(self):
        # Verify strict wrapping in 'content'
        res = self.fmt.data_part("my-type", {"foo": "bar"})
        # Expect: data: {"type": "my-type", "content": {"foo": "bar"}}
        self.assertSSE(res, "my-type", {"content": {"foo": "bar"}})
        
        # Verify wrapping of primitive
        res2 = self.fmt.data_part("my-primitive", "string-data")
        # Expect: data: {"type": "my-primitive", "content": "string-data"}
        self.assertSSE(res2, "my-primitive", {"content": "string-data"})

if __name__ == "__main__":
    unittest.main()
