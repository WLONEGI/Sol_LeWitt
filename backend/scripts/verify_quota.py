import asyncio
import os
import sys
from dotenv import load_dotenv

# Load .env BEFORE importing any project modules
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env")))

# Add the project root to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# NOW import settings and llm
from src.shared.config.settings import settings
from src.infrastructure.llm.llm import get_llm_by_type

async def test_quota():
    print(f"DEBUG: BASIC_MODEL={settings.BASIC_MODEL}")
    print(f"DEBUG: VERT_LOC={settings.VERTEX_LOCATION}")
    
    print("Testing Gemini Flash Quota with new region...")
    llm = get_llm_by_type("basic", streaming=False)
    
    tasks = []
    for i in range(5):
        tasks.append(llm.ainvoke(f"Repeat exactly: Quota test request {i}"))
        
    try:
        results = await asyncio.gather(*tasks)
        for i, res in enumerate(results):
            print(f"Response {i}: {res.content}")
        print("\n✅ Quota test successful! No 429 errors encountered for 5 concurrent requests.")
    except Exception as e:
        print(f"\n❌ Quota test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_quota())
