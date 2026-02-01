import asyncio
import json
import httpx
import sys

# Define colors for console output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
CYAN = "\033[96m"

async def main():
    url = "http://localhost:8000/api/chat/stream"
    
    # Payload to trigger some potential action
    payload = {
        "messages": [
            {"role": "user", "content": "Hello, please explain how you handle UI updates."}
        ],
        "debug": True
    }

    print(f"Connecting to {url}...")
    print(f"Payload: {json.dumps(payload, ensure_ascii=False)}")
    print("-" * 50)
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                print(f"Status Code: {response.status_code}")
                print(f"Headers: {response.headers}")
                
                if response.status_code != 200:
                    print(f"{RED}Error: Unexpected status code{RESET}")
                    error_body = await response.aread()
                    print(f"Response: {error_body.decode('utf-8')}")
                    return

                print(f"{GREEN}Connected! Listening for events...{RESET}\n")
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    # 4. Check for SSE prefix
                    if line.startswith("data:"):
                        print(f"{RED}FAILURE: Detected SSE 'data:' prefix! Expected raw JSON.{RESET}")
                        print(f"Line content: {line[:100]}...")
                        # Attempt to parse anyway for debugging
                        line = line.replace("data: ", "", 1)

                    # 1. Verify JSON validity
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        print(f"{RED}FAILURE: Line is not valid JSON{RESET}")
                        print(f"Line: {line}")
                        continue

                    event_type = data.get("event")
                    event_name = data.get("name")
                    
                    # 2. Check for ui_step_update
                    if event_type == "on_custom_event" and event_name == "ui_step_update":
                        print(f"\n{GREEN}[SUCCESS] Found 'ui_step_update' event!{RESET}")
                        print(json.dumps(data, indent=2, ensure_ascii=False))
                    
                    # 3. Check for standard LangGraph events
                    elif event_type == "on_chat_model_stream":
                        chunk = data.get("data", {}).get("chunk", {})
                        content = chunk.get("content", "")
                        if content:
                             print(f"{CYAN}{content}{RESET}", end="", flush=True)
                    
                    elif event_type == "on_custom_event":
                        # Other custom events
                        print(f"\n{YELLOW}[Custom Event] {event_name}{RESET}")
                        if "data" in data:
                            print(f"  Data: {str(data['data'])[:150]}...")
                            
                    elif event_type == "on_chain_start":
                         # Minimal log for start
                         pass
                         
                    elif event_type == "on_chain_end":
                         # Minimal log for end
                         pass
                         
                    else:
                        # Log other events briefly
                        # print(f"[Event] {event_type} - {event_name}")
                        pass

    except httpx.RequestError as e:
        print(f"\n{RED}Connection error detected: {e}{RESET}")
    except Exception as e:
        print(f"\n{RED}An error occurred: {e}{RESET}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped by user.")
