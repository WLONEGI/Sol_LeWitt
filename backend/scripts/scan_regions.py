import os
import asyncio
from dotenv import load_dotenv
from google import genai
import vertexai
from vertexai.generative_models import GenerativeModel

load_dotenv()
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")
REGIONS = ["us-central1", "us-west1", "us-east4", "asia-northeast1", "europe-west4", "us-east1"]

async def test_region(region):
    print(f"--- Testing Region: {region} ---")
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=region)
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents="Hello."
        )
        print(f"✅ Success in {region}!")
        return True
    except Exception as e:
        print(f"❌ Failed in {region}: {e}")
        return False

async def main():
    print(f"Scanning regions for Project: {PROJECT_ID}")
    for region in REGIONS:
        if await test_region(region):
            break

if __name__ == "__main__":
    asyncio.run(main())
