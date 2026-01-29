import os
import asyncio
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")

print(f"Testing Snippet with Project: {PROJECT_ID}")

def test_snippet():
    try:
        # User snippet adapted
        client = genai.Client(
            vertexai=True, 
            project=PROJECT_ID, 
            location="us-central1" # override 'global' to test if this SDK setup is what User means. 
            # Wait, user wrote location="global". I should test that first as it might be the key.
            # But Vertex AI usually requires specific regions. Let's try user's "global" first.
        )
        
        # NOTE: "global" location for Vertex AI often refers to specific resource types, 
        # but Generative AI on Vertex usually requires specific regions (us-central1, etc).
        # Let's try exactly what user provided first.
        try:
             client_global = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
             print("Initialized client with location='global'")
        except Exception as e:
             print(f"Initialization with 'global' failed: {e}")

        # The user code:
        client = genai.Client(
          vertexai=True, project=PROJECT_ID, location="us-central1", # Fallback to known region format for "is this the SDK" check
        )
        
        print(f"Client type: {type(client)}")
        print(f"Is Google Gen AI SDK? {isinstance(client, genai.Client)}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_snippet()
