import asyncio
import aiohttp
import json

async def test_stream():
    url = "http://127.0.0.1:8000/api/chat/stream"
    payload = {
        "messages": [
            {"role": "user", "content": "Hello, explain how you work."}
        ],
        "debug": True
    }
    
    print(f"Connecting to {url}...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                print(f"Status: {response.status}")
                if response.status != 200:
                    print(await response.text())
                    return

                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        if data.get("event") == "on_chain_start":
                            # Ignore noisy start events
                            continue
                        
                        print(f"[Event] Type: {data.get('event')} | Name: {data.get('name')}")
                        if data.get('event') == 'on_chat_model_stream':
                             # Show partial text
                             chunk = data.get('data', {}).get('chunk', {})
                             print(f"  -> Delta: {str(chunk)[:50]}...")
                    except Exception as e:
                        print(f"Failed to parse line: {line[:50]}... Error: {e}")

    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_stream())
