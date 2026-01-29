import os
import time
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types
import vertexai
from vertexai.generative_models import GenerativeModel
from langchain_google_vertexai import ChatVertexAI

# Load environment variables
load_dotenv()

PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION")
MODEL_ID = os.getenv("REASONING_MODEL", "gemini-2.5-flash") # Default to flash for specific test

print(f"=== Gemini 3.0 Connection Verification ===")
print(f"Project ID: {PROJECT_ID}")
print(f"Location: {LOCATION}")
print(f"Target Model: {MODEL_ID}")
print("==========================================\n")

if not PROJECT_ID or not LOCATION:
    print("ERROR: VERTEX_PROJECT_ID or VERTEX_LOCATION not set in .env")
    exit(1)

async def test_google_genai_sdk():
    print(f"--- Method 1: google-genai SDK (Vertex AI) ---")
    try:
        start_time = time.time()
        client = genai.Client(
            vertexai=True,
            project=PROJECT_ID,
            location=LOCATION
        )
        
        response = client.models.generate_content(
            model=MODEL_ID,
            contents="Hello, are you online? Reply with 'Yes, I am online.' only."
        )
        elapsed = time.time() - start_time
        print(f"✅ Success")
        print(f"⏱️ Latency: {elapsed:.4f}s")
        print(f"📝 Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    print("------------------------------------------------\n")

async def test_langchain_vertexai():
    print(f"--- Method 2: langchain-google-vertexai ---")
    try:
        start_time = time.time()
        llm = ChatVertexAI(
            model_name=MODEL_ID,
            project=PROJECT_ID,
            location=LOCATION,
            temperature=0
        )
        response = await llm.ainvoke("Hello, are you online? Reply with 'Yes, I am online.' only.")
        elapsed = time.time() - start_time
        print(f"✅ Success")
        print(f"⏱️ Latency: {elapsed:.4f}s")
        print(f"📝 Response: {response.content.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    print("------------------------------------------------\n")

async def test_vertexai_sdk():
    print(f"--- Method 3: vertexai SDK (Standard) ---")
    try:
        start_time = time.time()
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = GenerativeModel(MODEL_ID)
        response = await model.generate_content_async("Hello, are you online? Reply with 'Yes, I am online.' only.")
        elapsed = time.time() - start_time
        print(f"✅ Success")
        print(f"⏱️ Latency: {elapsed:.4f}s")
        print(f"📝 Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    print("------------------------------------------------\n")

async def main():
    await test_google_genai_sdk()
    await test_langchain_vertexai()
    await test_vertexai_sdk()

if __name__ == "__main__":
    asyncio.run(main())
