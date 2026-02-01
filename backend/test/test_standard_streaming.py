"""
Test script to verify if on_chat_model_stream events are being emitted.
This helps diagnose whether standard LangChain streaming works with ChatGoogleGenerativeAI.
"""
import asyncio
import aiohttp
import json
from datetime import datetime

async def test_stream():
    url = 'http://127.0.0.1:8000/api/chat/stream'
    payload = {
        'messages': [{'role': 'user', 'content': 'Say hello in one sentence'}],
        'debug': False
    }
    
    print(f"[{datetime.now().isoformat()}] Starting test...")
    print(f"URL: {url}")
    print(f"Payload: {json.dumps(payload)}")
    print("-" * 60)
    
    standard_stream_events = []
    custom_text_delta_events = []
    all_events = []
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=120)) as response:
                print(f"Status: {response.status}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        event_type = data.get('event', '')
                        event_name = data.get('name', '')
                        
                        all_events.append({'event': event_type, 'name': event_name})
                        
                        # Standard streaming event
                        if event_type == 'on_chat_model_stream':
                            print(f"[DEBUG] on_chat_model_stream full data: {json.dumps(data)}")
                            chunk = data.get('data', {}).get('chunk', {})
                            content = chunk.get('content', '') if isinstance(chunk, dict) else ''
                            standard_stream_events.append(content)
                            print(f"[STANDARD] on_chat_model_stream: '{content}'")
                        
                        # Custom event (our workaround)
                        if event_type == 'on_custom_event' and event_name == 'text_delta':
                            content = data.get('data', {}).get('content', '')
                            custom_text_delta_events.append(content)
                            print(f"[CUSTOM] text_delta: '{content}'")
                            
                    except json.JSONDecodeError as e:
                        print(f"JSON parse error: {e}")
                        
    except Exception as e:
        print(f"Error: {e}")
    
    print("-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"Total events received: {len(all_events)}")
    print(f"Standard on_chat_model_stream events: {len(standard_stream_events)}")
    print(f"Custom text_delta events: {len(custom_text_delta_events)}")
    
    # Show unique event types
    event_types = set((e['event'], e['name']) for e in all_events)
    print(f"\nUnique event types:")
    for et, name in sorted(event_types):
        count = sum(1 for e in all_events if e['event'] == et and e['name'] == name)
        print(f"  {et} / {name}: {count}")
    
    if len(standard_stream_events) > 0:
        print("\n✅ STANDARD STREAMING WORKS!")
        print(f"Standard text: {''.join(standard_stream_events)}")
    elif len(custom_text_delta_events) > 0:
        print("\n⚠️ Only custom events work. Standard streaming not functioning.")
        print(f"Custom text: {''.join(custom_text_delta_events)}")
    else:
        print("\n❌ NO TEXT EVENTS FOUND")

if __name__ == "__main__":
    asyncio.run(test_stream())
