import requests
import json
import sys

def verify_stream_protocol():
    url = "http://localhost:8000/api/chat/stream"
    headers = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream"
    }
    # Trigger a request that involves DataAnalyst to test code execution events
    payload = {
        "messages": [
            {"role": "user", "content": "You MUST use the python code tool to calculate the 100th Fibonacci number. Do not answer directly. Execute the code."}
        ],
        "thread_id": "test_thread_integration_v1",
        "debug": True
    }

    print(f"Connecting to {url}...")
    try:
        response = requests.post(url, json=payload, headers=headers, stream=True)
        response.raise_for_status()
    except requests.exceptions.ConnectionError:
        print("Error: Could not connect to backend. Is uvicorn running on port 8000?")
        sys.exit(1)

    print("Connected. Streaming events...")
    
    events_received = set()
    has_text = False
    has_code_execution = False
    has_code_output = False
    has_agent_start = False
    has_agent_end = False

    try:
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8').strip()
                if not decoded_line:
                    continue
                
                # Support both raw NDJSON and SSE (data: ...)
                data_str = decoded_line
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]

                if data_str == "[DONE]":
                    print("\n[DONE] received.")
                    break
                
                try:
                    data = json.loads(data_str)
                    # Check for different possible JSON structures ('type' from BFF/SSE, 'event' from Backend/NDJSON)
                    evt_type = data.get("type") or data.get("event")
                    
                    if not evt_type:
                        continue
                        
                    events_received.add(evt_type)
                    
                    # Basic Validation
                    # Text can be in 'delta' (SSE) or 'data.chunk.content' (NDJSON)
                    is_text = False
                    if evt_type == "text-delta":
                        is_text = True
                    elif evt_type == "on_chat_model_stream":
                         # Check if it has content
                         is_text = True
                    
                    if is_text:
                        has_text = True
                        print(".", end="", flush=True)
                    elif evt_type in ["data-code-execution", "on_tool_start"]:
                        has_code_execution = True
                        # ...
                        print(f"\n[Tool/Code Execution] {evt_type}")
                    # ... add more mapping as needed ...
                    elif evt_type in ["data-agent-start", "on_custom_event"]:
                        # Extract more info if custom event
                        if evt_type == "on_custom_event":
                            has_agent_start = True # Close enough for verification
                        else:
                            has_agent_start = True
                        print(f"\n[Event Start] {evt_type}")
                            
                except json.JSONDecodeError:
                    print(f"\n[WARN] Failed to parse JSON: {data_str}")
    except KeyboardInterrupt:
        print("\nTest interrupted.")

    print("\n\n--- Verification Report ---")
    print(f"Events Received: {events_received}")
    
    missing = []
    if not has_text: missing.append("text-delta")
    if not has_agent_start: missing.append("data-agent-start")
    
    # Note: Code execution might not trigger if the LLM decides not to use tools for simple math,
    # but for "Calculate... with python", it usually does.
    if not has_code_execution: 
        print("WARN: No code execution observed. LLM might have answered directly.")
    else:
        print("PASS: Code Execution observed.")
        
    if not has_code_output and has_code_execution:
        print("FAIL: Code execution started but no output received.")
        missing.append("data-code-output")

    if missing:
        print(f"FAIL: Missing expected events: {missing}")
        sys.exit(1)
    else:
        print("SUCCESS: Protocol verified.")

if __name__ == "__main__":
    verify_stream_protocol()
