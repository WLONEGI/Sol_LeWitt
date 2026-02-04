import asyncio
import sys
import os
from typing import Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.workflow.nodes.researcher import route_research
from src.core.workflow.state import ResearchSubgraphState
from src.shared.schemas import ResearchTask
from langgraph.types import Send
from src.app.app import CustomSerializer

async def test_serialization():
    print("=== Testing Researcher Serialization ===")
    
    # 1. Prepare state that triggers parallel dispatch
    tasks = [
        ResearchTask(id=1, perspective="Task 1", query_hints=[], priority="high", expected_output="..."),
        ResearchTask(id=2, perspective="Task 2", query_hints=[], priority="high", expected_output="...")
    ]
    state: ResearchSubgraphState = {
        "internal_research_tasks": tasks,
        "internal_research_results": [],
        "is_decomposed": True,
        "plan": [],
        "messages": [],
        "artifacts": {}
    }
    
    # 2. Call route_research to get Send objects
    print("Calling route_research...")
    result = route_research(state)
    
    if not isinstance(result, list) or not all(isinstance(x, Send) for x in result):
        print(f"FAILED: Expected list of Send objects, got {type(result)}")
        return
    
    print(f"Got {len(result)} Send objects.")
    
    # 3. Test CustomSerializer
    serializer = CustomSerializer()
    print("Testing serialization of Send objects...")
    
    for i, obj in enumerate(result):
        try:
            # Manually trigger serialization logic used in LangServe
            # LangServe uses dumps which calls default
            serialized = serializer.default(obj)
            print(f"  Send[{i}] serialized to: {serialized}")
            assert serialized is None, f"Expected None, got {serialized}"
        except Exception as e:
            print(f"  FAILED: Serialization of Send[{i}] raised {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return

    print("SUCCESS: CustomSerializer correctly handled Send objects.")

if __name__ == "__main__":
    asyncio.run(test_serialization())
