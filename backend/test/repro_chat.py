
import asyncio
import uuid
import httpx
import json

# Setup
BASE_URL = "http://127.0.0.1:8000"
THREAD_ID = str(uuid.uuid4())

async def run_test():
    async with httpx.AsyncClient(timeout=60.0) as client:
        print(f"--- Test Session: {THREAD_ID} ---")
        
        # 1. First Turn
        msg1 = [
            {"role": "user", "content": "こんにちは、元気ですか？"}
        ]
        print(f"\n[1] Sending first message: {msg1[0]['content']}")
        
        response1 = ""
        async with client.stream("POST", f"{BASE_URL}/api/chat/stream", json={
            "messages": msg1,
            "thread_id": THREAD_ID
        }) as r:
            if r.status_code != 200:
                print(f"Error: {r.status_code}, {await r.aread()}")
                return

            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("event") == "on_chat_model_stream":
                            chunk = data.get("data", {}).get("chunk", {})
                            content = chunk.get("content", "")
                            if content:
                                print(content, end="", flush=True)
                                response1 += content
                    except:
                        pass
        print("\n\nFirst turn completed.")
        
        # 2. Second Turn (Simulate Frontend sending full history)
        # We assume the backend would have appended the AI response to its state
        # But frontend sends: [User1, AI1(local), User2]
        
        msg2 = [
            {"role": "user", "content": "こんにちは、元気ですか？"},
            {"role": "assistant", "content": response1}, # Mocking what frontend might send
            {"role": "user", "content": "大阪の天気はどうですか？"}
        ]
        
        print(f"\n[2] Sending second message (with history): {msg2[-1]['content']}")
        
        response2 = ""
        async with client.stream("POST", f"{BASE_URL}/api/chat/stream", json={
            "messages": msg2,
            "thread_id": THREAD_ID
        }) as r:
            if r.status_code != 200:
                print(f"Error: {r.status_code}, {await r.aread()}")
                return

            async for line in r.aiter_lines():
                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:].strip())
                        if data.get("event") == "on_chat_model_stream":
                            chunk = data.get("data", {}).get("chunk", {})
                            content = chunk.get("content", "")
                            if content:
                                print(content, end="", flush=True)
                                response2 += content
                    except:
                        pass
                        
        print("\n\nSecond turn completed.")
        
        if response2:
            print("\n✅ Verification SUCCESS: Received response for second turn.")
        else:
            print("\n❌ Verification FAILED: No response for second turn.")

if __name__ == "__main__":
    asyncio.run(run_test())
