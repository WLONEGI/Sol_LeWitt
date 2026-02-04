
import asyncio
import os
import sys
from dotenv import load_dotenv

# Load .env from backend/.env explicitly
dotenv_path = os.path.join(os.getcwd(), 'backend', '.env')
load_dotenv(dotenv_path)

# Add backend directory to sys.path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage
from src.infrastructure.llm.llm import create_gemini_llm 
from src.shared.config.settings import settings

# Define a Pydantic model for structured output
class Step(BaseModel):
    id: int = Field(..., description="Step ID")
    instruction: str = Field(..., description="Instruction for the step")

class Plan(BaseModel):
    steps: list[Step] = Field(..., description="List of steps")

async def verify_streaming():
    print("--- Verifying Structured Output Streaming with Reasoning ---")
    
    model_name = os.environ.get("REASONING_MODEL")
    project_id = os.environ.get("VERTEX_PROJECT_ID")
    location = os.environ.get("VERTEX_LOCATION")
    
    if not model_name: 
         model_name = settings.REASONING_MODEL or "gemini-3-flash-preview"
    if not project_id:
         project_id = settings.VERTEX_PROJECT_ID or "aerobic-stream-483505-a0"
    if not location:
         location = settings.VERTEX_LOCATION or "global"
         
    print(f"Model: {model_name}")
    print(f"Project: {project_id}")
    print(f"Location: {location}")
    
    settings.REASONING_MODEL = model_name
    settings.VERTEX_PROJECT_ID = project_id
    settings.VERTEX_LOCATION = location
    settings.MAX_RETRIES = 3

    # 1. Initialize LLM with include_thoughts=True using the factory function
    llm = create_gemini_llm(
        model=model_name,
        project=project_id,
        location=location,
        include_thoughts=True,
        thinking_level="high",
        streaming=True
    )
    
    # 2. Bind structured output
    structured_llm = llm.with_structured_output(Plan)
    
    messages = [
        HumanMessage(content="Make a simple 2-step plan to clean a room.")
    ]
    
    print("\n--- Starting astream_events ---")
    try:
        async for event in structured_llm.astream_events(messages, version="v2"):
            event_type = event["event"]
            
            if event_type == "on_chat_model_stream":
                chunk = event["data"]["chunk"]
                content = chunk.content
                print(f"[CHUNK] {chunk}")
                
            elif event_type == "on_chain_end":
                if event["name"] == "_StructuredOutputRunnable":
                     print(f"  >>> [Structured Output Result]: {event['data'].get('output')}")

    except Exception as e:
        print(f"Error during streaming: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(verify_streaming())
