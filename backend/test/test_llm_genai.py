#!/usr/bin/env python3
"""
Test script to verify ChatGoogleGenerativeAI can call Gemini via Vertex AI.
"""
import asyncio
import os
import sys

# Add backend to path
sys.path.insert(0, "/Users/negishi/develop/AI_Slide_with_nano_banana/backend")

from langchain_google_genai import ChatGoogleGenerativeAI, HarmCategory, HarmBlockThreshold

async def test_chat_google_genai():
    """Test ChatGoogleGenerativeAI with project parameter (Vertex AI mode)."""
    
    project_id = os.environ.get("VERTEX_PROJECT_ID", "aerobic-stream-483505-a0")
    location = os.environ.get("VERTEX_LOCATION", "asia-northeast1")
    model = "gemini-2.0-flash"  # Use a known working model
    
    print(f"Testing ChatGoogleGenerativeAI with:")
    print(f"  project: {project_id}")
    print(f"  location: {location}")
    print(f"  model: {model}")
    print("-" * 50)
    
    safety_settings = {
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_ONLY_HIGH,
    }
    
    try:
        llm = ChatGoogleGenerativeAI(
            model=model,
            project=project_id,
            location=location,
            temperature=0.0,
            streaming=False,
            safety_settings=safety_settings,
        )
        
        print("LLM instance created successfully.")
        print(f"Calling model...")
        
        # Simple invoke test
        response = await llm.ainvoke("Say 'Hello' in Japanese")
        print(f"\n✅ Response: {response.content}")
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_chat_google_genai())
    sys.exit(0 if result else 1)
