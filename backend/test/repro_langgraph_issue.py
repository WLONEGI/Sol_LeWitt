import asyncio
import os
from src.core.workflow.service import initialize_graph, _manager

async def test():
    await initialize_graph()
    graph = _manager.get_graph()
    print(f"Graph config specs: {graph.config_specs}")
    
    input_data = {"messages": [{"role": "user", "content": "Hello"}]}
    config = {"configurable": {"thread_id": "test-id"}}
    
    print("Testing astream_events...")
    try:
        async for event in graph.astream_events(input_data, config, version="v2"):
            if event["event"] == "on_chat_model_stream":
                print(f"Event: {event['event']}, Content: {event['data']['chunk'].content}")
            else:
                print(f"Event: {event['event']}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await _manager.close()

if __name__ == "__main__":
    asyncio.run(test())
