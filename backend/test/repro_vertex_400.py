import asyncio
import os
from langchain_core.messages import HumanMessage
from src.core.workflow.nodes.coordinator import CoordinatorOutput
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template

# Mock state
state = {
    # Revert to standard valid input
    "messages": [HumanMessage(content="Hello")],
    "analysis_report": "",
    "user_profile": "",
    "current_plan": ""
}

async def reproduce():
    print("🚀 Starting confirmation of FIX for Vertex AI 400 Error...")
    
    # 1. Use the ACTUAL updated function
    prompt_name = "coordinator"
    messages = apply_prompt_template(prompt_name, state)
    
    print(f"Messages prepared: {len(messages)} items")
    print(f"Message 0 type: {type(messages[0])}")
    print(f"Message 0 content: {messages[0].content[:50]}...")
    
    # 2. Initialize LLM
    try:
        from src.shared.config import settings
        # Force the model causing issue
        settings.HIGH_REASONING_MODEL = "gemini-3-pro-preview"
        settings.VERTEX_PROJECT_ID = "aerobic-stream-483505-a0"
        settings.VERTEX_LOCATION = "global"
    except ImportError:
        pass

    llm = get_llm_by_type("high_reasoning") # coordinator maps to high_reasoning
    print(f"LLM initialized: {llm.model_name}")

    # 3. Call structured output
    structured_llm = llm.with_structured_output(CoordinatorOutput)
    
    try:
        print("invoke calling...")
        result = await structured_llm.ainvoke(messages)
        print("✅ Success!")
        print(result)
    except Exception as e:
        print("\n❌ Caught Exception:")
        print(e)

if __name__ == "__main__":
    asyncio.run(reproduce())
