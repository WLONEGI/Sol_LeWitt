import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")

print(f"=== User Snippet Verification ===")
print(f"Project: {PROJECT_ID}")
print(f"Location: global (User Pattern)")
print("=================================\n")

def test_model(model_name):
    print(f"--- Testing Model: {model_name} ---")
    try:
        # User Logic: location="global"
        client = genai.Client(
            vertexai=True, 
            project=PROJECT_ID, 
            location="global"
        )
        
        response = client.models.generate_content(
            model=model_name,
            contents="Hello, this is a test from the global endpoint."
        )
        print(f"✅ Success")
        print(f"📝 Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")
    print("---------------------------------\n")

if __name__ == "__main__":
    # Test 1: High Reasoning (User's example model)
    test_model("gemini-3-flash-preview")
    
    # Test 2: Known Working Model (from previous test)
    test_model("gemini-2.5-flash")
