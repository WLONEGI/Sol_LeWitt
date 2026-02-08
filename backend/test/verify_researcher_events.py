import asyncio
import sys
import os
from typing import Any

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core.workflow.nodes.researcher import build_researcher_subgraph
from src.core.workflow.state import ResearchSubgraphState
from src.shared.schemas import ResearchTask
from langchain_core.runnables import RunnableConfig

async def test_researcher_events():
    print("=== Testing Researcher Events Streaming ===")
    
    # 1. Prepare Subgraph
    app = build_researcher_subgraph()
    
    # 2. Prepare Tasks
    tasks = [
        ResearchTask(
            id=1, 
            perspective="Test Topic", 
            query_hints=["test query"], 
            priority="high", 
            expected_output="Detailed output."
        )
    ]
    
    state: ResearchSubgraphState = {
        "internal_research_tasks": tasks,
        "internal_research_results": [],
        "is_decomposed": True,
        "plan": [{"id": "test_step", "capability": "researcher", "status": "in_progress", "instruction": "Test research"}],
        "messages": [],
        "artifacts": {}
    }
    
    config = RunnableConfig(configurable={"thread_id": "test_event_thread"})
    
    print("Starting astream_events...")
    
    event_counts = {
        "research_worker_start": 0,
        "research_worker_token": 0,
        "research_worker_complete": 0,
        "citation_metadata": 0
    }
    
    found_send = False
    
    try:
        async for event in app.astream_events(state, config, version="v2"):
            event_type = event.get("event")
            name = event.get("name")
            
            # Check for custom events
            if event_type == "on_custom_event":
                custom_name = event.get("name")
                if custom_name in event_counts:
                    event_counts[custom_name] += 1
                    print(f"  [Custom Event] {custom_name}")
            
            # Check for node completion or other signals
            if event_type == "on_chain_end" and name == "manager":
                # Check output for Send objects or END
                output = event.get("data", {}).get("output")
                if isinstance(output, list) and any(str(x).startswith("Send(") for x in output):
                    found_send = True
                    print(f"  [Manager Output] Found Send objects: {output}")

    except Exception as e:
        print(f"  FAILED: astream_events raised {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n--- Event Statistics ---")
    for name, count in event_counts.items():
        print(f"{name}: {count}")
    
    print(f"Found Send objects in manager output: {found_send}")
    
    # Assertions
    success = True
    if event_counts["research_worker_start"] == 0:
        print("ERROR: No research_worker_start event found.")
        success = False
    if event_counts["research_worker_token"] == 0:
        print("ERROR: No research_worker_token event found.")
        success = False
    if event_counts["research_worker_complete"] == 0:
        print("ERROR: No research_worker_complete event found.")
        success = False
    # citation_metadata might be 0 if LLM doesn't provide it, so we don't strictly fail on it here
        
    if success:
        print("\nSUCCESS: All expected core events were captured.")
    else:
        print("\nFAILED: Some events were missing.")

if __name__ == "__main__":
    asyncio.run(test_researcher_events())
