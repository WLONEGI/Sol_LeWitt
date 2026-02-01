import aiohttp
import asyncio
import json

async def verify_stream():
    url = "http://localhost:8000/api/chat/stream"
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "thread_id": "test_verification_thread"
    }

    print(f"Connecting to {url}...")
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as response:
            print(f"Status: {response.status}")
            print(f"Content-Type: {response.headers.get('Content-Type')}")
            
            async for line in response.content:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                
                print(f"Received: {line}")
                
                # Support both raw NDJSON and SSE (data: ...)
                json_str = line
                if line.startswith("data: "):
                    json_str = line[6:]
                
                try:
                    data = json.loads(json_str)
                    # Check for different possible JSON structures
                    evt_type = data.get('type') or data.get('event')
                    print(f"✅ Valid JSON: type/event={evt_type}")
                except json.JSONDecodeError:
                    if json_str == "[DONE]":
                        print("✅ Received [DONE]")
                    else:
                        print(f"❌ Invalid JSON: {json_str}")

if __name__ == "__main__":
    asyncio.run(verify_stream())
