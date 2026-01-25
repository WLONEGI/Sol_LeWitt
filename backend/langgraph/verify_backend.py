
import asyncio
import httpx
import sys
import json

BASE_URL = "http://localhost:8000"

async def check_health(client):
    print("Checking /health...")
    try:
        response = await client.get(f"{BASE_URL}/health")
        print(f"Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error checking health: {e}")
        return False

async def check_history(client):
    print("\nChecking /api/history...")
    try:
        thread_id = "test-thread-verification"
        response = await client.get(f"{BASE_URL}/api/history", params={"thread_id": thread_id})
        print(f"Status: {response.status_code}")
        # It might be empty or 404 if no history, but let's see. 
        # Typically returns list.
        if response.status_code == 200:
             print(f"Response: {response.json()}")
        else:
             print(f"Response Error: {response.text}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error checking history: {e}")
        return False

async def check_chat_stream(client):
    print("\nChecking /api/chat/stream...")
    payload = {
        "messages": [{"role": "user", "content": "Hello, this is a test check."}],
        "debug": True,
        "thread_id": "test-thread-verification"
    }
    
    print("Connecting to stream...")
    try:
        async with client.stream("POST", f"{BASE_URL}/api/chat/stream", json=payload, timeout=30.0) as response:
            print(f"Status: {response.status_code}")
            if response.status_code != 200:
                print(f"Response: {response.headers}")
                print(f"Response Error: {await response.aread()}")
                return False
            
            print("Stream opened. Reading events...")
            count = 0
            async for line in response.aiter_lines():
                if line:
                    print(f"Received: {line}")
                    count += 1
                    # Verify we are receiving data
                    if count >= 3: 
                        print("Verified receiving events. success.")
                        break
            
        print("Stream check finished.")
        return True
    except Exception as e:
        print(f"Error checking chat stream: {e}")
        return False

async def main():
    print("Starting Verification Script...")
    async with httpx.AsyncClient() as client:
        # 1. Wait for health
        retries = 5
        server_up = False
        for i in range(retries):
            if await check_health(client):
                server_up = True
                break
            print(f"Waiting for server... ({i+1}/{retries})")
            await asyncio.sleep(2)
        
        if not server_up:
            print("Server failed to start or is unreachable.")
            sys.exit(1)

        # 2. Check History
        await check_history(client)

        # 3. Check Chat Stream
        await check_chat_stream(client)

if __name__ == "__main__":
    asyncio.run(main())
