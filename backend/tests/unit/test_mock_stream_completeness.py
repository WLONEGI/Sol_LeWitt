
import unittest
import asyncio
import json
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))

from src.shared.utils.mock_stream_generator import generate_mock_stream

class TestMockStreamCompleteness(unittest.TestCase):
    def test_mock_stream_events(self):
        """
        Consumes the mock stream and verifies that all expected Datapart types 
        are emitted with valid JSON structure.
        """
        async def run_test():
            events = []
            async for chunk in generate_mock_stream():
                # Chunk format: "data: {json}\n\n"
                if not chunk.strip(): continue
                
                prefix = "data: "
                self.assertTrue(chunk.startswith(prefix), f"Invalid chunk format: {chunk}")
                json_str = chunk[len(prefix):].strip()
                try:
                    event = json.loads(json_str)
                    events.append(event)
                except json.JSONDecodeError:
                    self.fail(f"Failed to decode JSON: {json_str}")
            
            # Verify Presence of Key Event Types
            event_types = [e.get("type") for e in events]
            
            # Helper to check type
            def assert_has_type(t):
                self.assertIn(t, event_types, f"Missing event type: {t}")

            assert_has_type("data-workflow-start")
            assert_has_type("data-phase-change")
            assert_has_type("date-agent-start") if "date-agent-start" in event_types else assert_has_type("data-agent-start")
            
            assert_has_type("reasoning-start")
            assert_has_type("reasoning-delta")
            assert_has_type("reasoning-end")
            
            assert_has_type("tool-input-available") # Converted from tool_call
            assert_has_type("data-code-execution")
            
            assert_has_type("data-plan-update")
            
            assert_has_type("text-start")
            assert_has_type("text-delta")
            
            assert_has_type("data-slide_outline")
            assert_has_type("data-visualizer-progress")
            assert_has_type("data-artifact-ready")
            
            assert_has_type("file")
            assert_has_type("data-title-generated")
            assert_has_type("finish")
            
            print(f"\n✅ Verified {len(events)} events covering all required Dataparts.")

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_test())
        loop.close()

if __name__ == "__main__":
    unittest.main()
