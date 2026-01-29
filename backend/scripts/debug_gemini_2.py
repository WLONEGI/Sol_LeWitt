import os
import asyncio
from dotenv import load_dotenv
from google import genai
import vertexai
from vertexai.language_models import TextGenerationModel

load_dotenv()
PROJECT_ID = os.getenv("VERTEX_PROJECT_ID")
LOCATION = os.getenv("VERTEX_LOCATION")

print(f"Debug Project: {PROJECT_ID}")
print(f"Debug Location: {LOCATION}")

def test_legacy():
    print(f"\n--- Testing Legacy: 'text-bison@001' ---")
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        model = TextGenerationModel.from_pretrained("text-bison@001")
        response = model.predict("Hello")
        print(f"✅ Success! Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")

async def test_genai(model_name):
    print(f"\n--- Testing GenAI: '{model_name}' ---")
    try:
        client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)
        response = client.models.generate_content(
            model=model_name,
            contents="Hello."
        )
        print(f"✅ Success! Response: {response.text.strip()}")
    except Exception as e:
        print(f"❌ Failed: {e}")

async def main():
    test_legacy()
    await test_genai('gemini-1.5-flash')
    await test_genai('gemini-1.0-pro')
    await test_genai('gemini-pro')

if __name__ == "__main__":
    asyncio.run(main())
