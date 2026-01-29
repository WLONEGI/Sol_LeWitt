import os
import asyncio
from dotenv import load_dotenv
from google import genai
import vertexai
from vertexai.generative_models import GenerativeModel

load_dotenv()
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION")

print(f"Debug Project: {PROJECT_ID}")
print(f"Debug Location: {LOCATION}")

async def test_model(model_name, label):
    print(f"\n--- Testing {label}: '{model_name}' ---")
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        # Try generate
        response = client.models.generate_content(
            model=model_name,
            contents="Hello."
        )
        print(f"✅ Success! Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")

async def main():
    # 1. Baseline
    await test_model('gemini-1.5-flash-001', "Baseline (1.5 Flash)")
    
    # 2. Target Short
    await test_model('gemini-3-flash-preview', "Target Short")
    
    # 3. Target Full
    await test_model('publishers/google/models/gemini-3-flash-preview', "Target Full Path")

if __name__ == "__main__":
    asyncio.run(main())
