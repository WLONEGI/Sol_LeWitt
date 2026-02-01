#!/usr/bin/env python3
"""
Test script to verify ChatVertexAI can call Gemini via Vertex AI.
Uses .env file for configuration.
"""
import asyncio
import os
import sys

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Add backend to path
sys.path.insert(0, "/Users/negishi/develop/AI_Slide_with_nano_banana/backend")

from langchain_google_vertexai import ChatVertexAI, HarmBlockThreshold, HarmCategory

async def test_chat_vertex_ai():
    """Test ChatVertexAI with Vertex AI."""
    
    project_id = os.environ.get("VERTEX_PROJECT_ID", "aerobic-stream-483505-a0")
    location = os.environ.get("VERTEX_LOCATION", "global")
    model = "gemini-3-flash-preview"  # Use gemini-3-flash-preview for testing
    
    print(f"Testing ChatVertexAI with:")
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
        llm = ChatVertexAI(
            model=model,
            project=project_id,
            location=location,
            temperature=0.0,
            streaming=True,
            safety_settings=safety_settings,
        )
        
        print("✅ LLM instance created successfully.")
        print(f"Calling model...")
        
        # Simple invoke test
        response = await llm.ainvoke("Say 'Hello' in Japanese. Reply in one word only.")
        print(f"\n✅ Response: {response.content}")
        return True
        
    except Exception as e:
        print(f"\n❌ Error: {type(e).__name__}: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_chat_vertex_ai())
    sys.exit(0 if result else 1)
