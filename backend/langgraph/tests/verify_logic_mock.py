import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph.graph_types import State
from src.workflow import run_agent_workflow_async

# Dummy Data
MOCK_COORDINATOR_OUTPUT = {
    "is_slide_generation_task": True,
    "user_intent": "Create slides",
    "required_info_gathered": True,
    "missing_info": [],
    "reasoning": "Standard request",
    "clarification_question": None
}

MOCK_PLANNER_OUTPUT = {
    "steps": [
        {
            "id": 1,
            "role": "storywriter",
            "instruction": "Draft a slide about AI.",
            "description": "Drafting",
            "status": "pending"
        }
    ]
}

MOCK_STORYWRITER_OUTPUT = {
    "execution_summary": "スライドを1枚作成しました。",
    "slides": [
        {
            "slide_number": 1,
            "title": "AI Override",
            "bullet_points": ["Point 1", "Point 2"]
        }
    ]
}

def mock_get_llm_by_type(model_type):
    """Return a mock LLM that returns structured output based on calls."""
    mock_llm = MagicMock()
    
    # We need to simulate .with_structured_output().invoke()
    # But since nodes.py calls:
    #   structured_llm = llm.with_structured_output(Schema)
    #   result = structured_llm.invoke(messages)
    #
    # We need to return an object that has an invoke method.
    
    mock_structured_llm = MagicMock()
    
    def side_effect_invoke(input_data):
        # Determine based on input messages which agent this is
        # Or simpler: since we know the flow, we can yield responses in order?
        # But 'get_llm_by_type' is called for each node.
        pass

    # However, 'get_llm_by_type' returns the base LLM.
    # .with_structured_output(...) returns the structured one.
    
    # Let's patch at the `nodes.py` level or make the mock smart enough.
    # The simplest way for this script is to return "success" objects.
    
    # We will implement a dynamic side effect
    return mock_llm

class MockStructuredLLM:
    def __init__(self, output_data):
        self.output_data = output_data
    
    def invoke(self, *args, **kwargs):
        # Return a Pydantic-like object (just a SimpleNamespace or Mock)
        # But the code expects Pydantic models (Schema).
        # We should import the schemas and instantiate them!
        return self.output_data

async def run_verification():
    print("Starting Logic Verification...")
    
    with patch("src.graph.nodes.get_llm_by_type") as mock_get_llm:
        with patch("src.graph.nodes.apply_prompt_template") as mock_apply:
            mock_apply.return_value = [{"role": "user", "content": "dummy"}] # Fast track
            
            # Setup specific responses for each node
            # This is tricky because `get_llm_by_type` is called inside each node function.
            # We need to return different objects depending on the context?
            # Or we can make `with_structured_output` return different mocks based on schema?
            
            from src.schemas.outputs import PlannerOutput, StorywriterOutput, SlideContent, TaskStep
            
            # 1. Planner Mock
            planner_response = PlannerOutput(steps=[
                TaskStep(id=1, role="storywriter", instruction="Test", title="Mock Task", description="Test", status="pending")
            ])
            planner_llm = MagicMock()
            planner_llm.invoke.return_value = planner_response

            # 2. Storywriter Mock
            story_response = StorywriterOutput(
                execution_summary="Mocked Summary",
                slides=[SlideContent(slide_number=1, title="Mock", bullet_points=[])]
            )
            story_llm = MagicMock()
            story_llm.invoke.return_value = story_response

            # 3. Coordinator Mock (doesn't use with_structured_output in the same way? Check node)
            # Coordinator uses `llm.with_structured_output(CoordinatorOutput)`
            from langchain_core.messages import AIMessage

            # 3. Coordinator Logic (Direct Invoke)
            coord_response = AIMessage(content="handoff_to_planner: Yes. I am handing off.")
            
            # Dispatcher for with_structured_output
            def with_structured_output_side_effect(schema, **kwargs):
                mock_struct = MagicMock()
                if schema == PlannerOutput:
                    mock_struct.invoke.return_value = planner_response
                elif schema == StorywriterOutput:
                    mock_struct.invoke.return_value = story_response
                # Add other agents if needed
                return mock_struct

            mock_base_llm = MagicMock()
            # Handle Direct Invoke (Coordinator)
            mock_base_llm.invoke.return_value = coord_response
            # Handle Structured Output (Planner, Workers)
            mock_base_llm.with_structured_output.side_effect = with_structured_output_side_effect
            
            mock_get_llm.return_value = mock_base_llm

            # RUN
            final_state = await run_agent_workflow_async("Test Input", debug=True)
            
            print("\n=== Verification Results ===")
            plan = final_state.get("plan", [])
            print(f"Plan Steps: {len(plan)}")
            
            if len(plan) == 0:
                print("❌ Plan is empty! Planner failure.")
                return

            step1 = plan[0]
            print(f"Step 1 Status: {step1['status']}")
            print(f"Step 1 Summary: {step1['result_summary']}")
            
            if step1['status'] == 'complete' and step1['result_summary'] == "Mocked Summary":
                print("✅ Planner -> Supervisor -> Storywriter -> Supervisor flow confirms Append/Summary logic.")
                print("✅ Execution Summary was correctly captured and stored in Plan.")
            else:
                print("❌ Verification Failed: Logic did not produce expected state.")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_verification())
