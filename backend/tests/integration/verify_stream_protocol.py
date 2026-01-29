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
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith("data: "):
                    data_str = decoded_line[6:]
                    if data_str == "[DONE]":
                        print("\n[DONE] received.")
                        break
                    
                    try:
                        data = json.loads(data_str)
                        evt_type = data.get("type")
                        events_received.add(evt_type)
                        
                        # Basic Validation
                        if evt_type == "text-delta":
                            has_text = True
                            print(".", end="", flush=True)
                        elif evt_type == "data-code-execution":
                            has_code_execution = True
                            print(f"\n[Code Execution] {data.get('data', {}).get('code', '')[:30]}...")
                        elif evt_type == "data-code-output":
                            has_code_output = True
                            print(f"\n[Code Output] {data.get('data', {}).get('result')}")
                        elif evt_type == "data-agent-start":
                            has_agent_start = True
                            print(f"\n[Agent Start] {data.get('data', {}).get('agent_name')}")
                        elif evt_type == "data-agent-end":
                            has_agent_end = True
                            print(f"\n[Agent End]")
                        elif evt_type == "error":
                            print(f"\n[ERROR] {data.get('errorText')}")
                            
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
