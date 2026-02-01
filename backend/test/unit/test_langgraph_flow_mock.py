import pytest
import datetime
from unittest.mock import MagicMock, patch, AsyncMock, Mock
from typing import Any, AsyncIterator, Dict, List, Optional
from pydantic import BaseModel

from langchain_core.messages import AIMessage, HumanMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from src.core.workflow.builder import build_graph
from src.core.workflow.state import State
from src.core.workflow.nodes.coordinator import CoordinatorDecision
from src.shared.schemas import PlannerOutput, TaskStep, VisualizerOutput, ImagePrompt, ThoughtSignature

# ==========================================
# 1. Mock Infrastructure
# ==========================================

class MockChunk:
    """Mimics a streaming chunk from ChatGoogleGenerativeAI."""
    def __init__(self, content):
        self.content = content

class MockLLM:
    """
    Mock LLM that can be pre-programmed with responses based on the caller agent.
    """
    def __init__(self, responses: Dict[str, Any]):
        """
        Args:
            responses: Map of agent_name -> response_object (Pydantic model or str)
                       Keys should match the role names: "coordinator", "reasoning" (planner), "storywriter", "visualizer", "basic" (supervisor)
        """
        self.responses = responses
        self.calls = []

    def bind(self, tools: Optional[List[Any]] = None):
        """Mock bind method to support tool binding."""
        return self

    async def ainvoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        self.calls.append({"type": "invoke", "input": input, "kwargs": kwargs})
        
        # Heuristic to determine which response to return based on input messages or kwargs
        # This part is tricky because 'get_llm_by_type' returns the LLM, and we don't know the caller name directly here
        # unless we infer it from the prompt content or configured response type.
        
        # For this test, we'll assume the test setup configures the mock appropriately or we check the requested response_format.
        response_format = kwargs.get("response_format")
        
        if response_format == CoordinatorDecision:
            return self.responses.get("coordinator")
        elif response_format == PlannerOutput:
            return self.responses.get("planner")
        elif response_format == VisualizerOutput:
            return self.responses.get("visualizer")
        
        # Fallback for standard text generation (Storywriter uses generic LLM but expects string/message)
        # Check messages to potentialy identify storywriter/researcher context if needed
        messages = input
        last_msg = messages[-1].content if messages else ""
        
        if "Visualizer" in str(messages) and "Instruction" in str(messages):
             # Visualizer text part (should be structured but safety fallback)
             pass 

        # Default string response (e.g. for Supervisor or simple text generation)
        return AIMessage(content=self.responses.get("default", "Mock Response"))

    async def astream(self, input: Any, config: Optional[Dict] = None, **kwargs) -> AsyncIterator[MockChunk]:
        self.calls.append({"type": "stream", "input": input, "kwargs": kwargs})
        
        # Determine response content
        content = "Mock Stream Response"
        
        # Simple heuristic for Supervisor report
        messages = input
        if isinstance(messages, list) and len(messages) > 0:
             # Check prompt for supervisor indicators
             prompt_str = str(messages)
             if "supervisor" in prompt_str.lower() or "report" in prompt_str.lower():
                 content = self.responses.get("supervisor", "Supervisor Report")
             # Check for Coordinator handoff
             elif "Task: Generate a polite" in prompt_str:
                 content = self.responses.get("coordinator_handoff", "Starting planning...")
        
        # Yield the content in chunks
        chunk_size = 5
        for i in range(0, len(content), chunk_size):
            yield MockChunk(content=content[i:i+chunk_size])


# ==========================================
# 2. Test Scenarios
# ==========================================

@pytest.fixture
def mock_gcs_upload():
    # Patch where it is USED, because visualizer.py imports it directly
    with patch("src.core.workflow.nodes.visualizer.upload_to_gcs", new_callable=Mock) as mock:
        mock.return_value = "https://mock.gcs/image.png"
        yield mock

@pytest.fixture
def mock_image_gen():
    with patch("src.domain.designer.generator.generate_image", new_callable=MagicMock) as mock:
        mock.return_value = (b"fake_image_bytes", "fake_token")
        yield mock

@pytest.fixture
def mock_db_ops():
    with patch("src.core.workflow.nodes.coordinator._generate_and_save_title", new_callable=AsyncMock) as mock:
        yield mock

@pytest.fixture
def mock_llm_factory(mock_responses):
    mock_llm = MockLLM(responses=mock_responses)
    
    # We must patch get_llm_by_type in all modules where it is imported directly
    # because they use 'from src.infrastructure.llm.llm import get_llm_by_type'
    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", return_value=mock_llm), \
         patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=mock_llm), \
         patch("src.core.workflow.nodes.visualizer.get_llm_by_type", return_value=mock_llm), \
         patch("src.core.workflow.nodes.supervisor.get_llm_by_type", return_value=mock_llm), \
         patch("src.core.workflow.nodes.storywriter.get_llm_by_type", return_value=mock_llm):
        yield mock_llm

from langgraph.checkpoint.memory import MemorySaver

@pytest.mark.asyncio
async def test_langgraph_happy_path(mock_gcs_upload, mock_image_gen, mock_db_ops):
    """
    Scenario A: Happy Path (Standard Flow)
    Coordinator -> Planner -> Supervisor -> Visualizer -> Supervisor -> End
    """
    # ... Response Prep ...
    # Coordinator Decision
    coordinator_resp = CoordinatorDecision(
        decision="handoff_to_planner",
        reasoning="User wants slides."
    )
    
    planner_resp = PlannerOutput(
        steps=[
            TaskStep(
                id=1,
                role="visualizer",
                title="Create Slide Image",
                instruction="Generate a cool cyberpunk slide.",
                description="Visualizer step",
                status="pending",
                result_summary=None
            )
        ]
    )
    
    visualizer_resp = VisualizerOutput(
        prompts=[
            ImagePrompt(
                slide_number=1,
                layout_type="title_and_content",
                structured_prompt=None,
                image_generation_prompt="Cyberpunk city",
                visual_style="Cyberpunk",
                main_title="Future",
                rationale="Visualizing the future.",
                generated_image_url=None,
                thought_signature=None
            )
        ],
        execution_summary="Created 1 slide image."
    )
    
    mock_responses = {
        "coordinator": coordinator_resp,
        "coordinator_handoff": "Confirming request...",
        "planner": planner_resp,
        "visualizer": visualizer_resp,
        "supervisor": "Progress is good."
    }
    
    # Patch settings.RESPONSE_FORMAT (it is used in create_worker_response)
    # We need to patch the instance 'settings' in the module that uses it: src.core.workflow.nodes.common
    # OR better, since 'settings' is imported as a singleton, we can modify it directly or patch it.
    
    with patch("src.core.workflow.nodes.common.settings") as mock_settings:
         mock_settings.RESPONSE_FORMAT = "## Content\n{content}"  
         
         # Use the patching fixture - refactored to be cleaner
         with patch("src.core.workflow.nodes.coordinator.get_llm_by_type") as m1, \
              patch("src.core.workflow.nodes.planner.get_llm_by_type") as m2, \
              patch("src.core.workflow.nodes.visualizer.get_llm_by_type") as m3, \
              patch("src.core.workflow.nodes.supervisor.get_llm_by_type") as m4:
              
             mock_llm = MockLLM(responses=mock_responses)
             m1.return_value = mock_llm
             m2.return_value = mock_llm
             m3.return_value = mock_llm
             m4.return_value = mock_llm
             
             # 3. Build Graph with Checkpointer
             checkpointer = MemorySaver()
             graph = build_graph(checkpointer=checkpointer)
             
             # 4. Input State
             initial_state = {
                 "messages": [HumanMessage(content="Create a cyberpunk slide.")],
                 "plan": [],
                 "artifacts": {}
             }
             
             # 5. Execute Graph
             final_state = None
             current_config = {"configurable": {"thread_id": "test_thread"}}
             step_count = 0
             
             # Pass 1: Runs until interrupt
             async for event in graph.astream(initial_state, current_config, stream_mode="values"):
                 step_count += 1
                 final_state = event
                 
             print(f"Post-Planner State Plan: {final_state.get('plan')}")
             
             # Resume Graph
             async for event in graph.astream(None, current_config, stream_mode="values"):
                  step_count += 1
                  final_state = event
                  current_plan = event.get("plan", [])
                  completed_steps = [s for s in current_plan if s["status"] == "complete"]
                  print(f"DEBUG: Step {step_count} - Completed: {len(completed_steps)}")
     
             # 6. Verify Results
             assert len(final_state["plan"]) == 1
             assert final_state["plan"][0]["status"] == "complete"
             assert final_state["plan"][0]["role"] == "visualizer"
             
             visual_artifacts = {k: v for k, v in final_state["artifacts"].items() if k.endswith("_visual")}
             assert len(visual_artifacts) > 0
             
             mock_gcs_upload.assert_called()
             print("✅ Happy Path Test Passed")


@pytest.mark.asyncio
async def test_langgraph_edge_case_direct_reply(mock_gcs_upload, mock_image_gen, mock_db_ops):
    """
    Scenario B: Coordinator acts as chatbot (No Plan)
    Coordinator -> End
    """
    
    coordinator_resp = CoordinatorDecision(
        decision="reply_to_user",
        reasoning="User just said hello."
    )
    
    mock_responses = {
        "coordinator": coordinator_resp,
    }
    
    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type") as m1:
        mock_llm = MockLLM(responses=mock_responses)
        m1.return_value = mock_llm
        
        graph = build_graph()
        
        initial_state = {
            "messages": [HumanMessage(content="Hello there!")],
            "plan": [],
            "artifacts": {}
        }
        
        final_state = None
        async for event in graph.astream(initial_state, stream_mode="values"):
            final_state = event
            
        assert len(final_state["plan"]) == 0
        
        last_msg = final_state["messages"][-1]
        assert isinstance(last_msg, AIMessage)
        assert last_msg.name == "coordinator"
        
        print("✅ Edge Case Test Passed")
