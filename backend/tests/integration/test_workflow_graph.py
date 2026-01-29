import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage
from langgraph.checkpoint.memory import MemorySaver

from src.core.workflow.builder import build_graph
from src.shared.schemas import PlannerOutput, TaskStep, StorywriterOutput, VisualizerOutput, DataAnalystOutput, SlideContent
from src.core.workflow.nodes.coordinator import CoordinatorDecision

@pytest.fixture
def mock_get_llm():
    """
    Override global mock to patch 'get_llm_by_type' in ALL node modules.
    Yields the Mock object representing 'get_llm_by_type' function.
    """
    # This mock represents the 'get_llm_by_type' function itself
    mock_factory = MagicMock()
    
    # Default behavior: returns a default LLM mock
    default_llm = MagicMock()
    default_llm.invoke.return_value = AIMessage(content="Default Mock Response")
    mock_factory.return_value = default_llm
    
    # Patch all locations using the SAME mock object (`new=mock_factory`)
    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", new=mock_factory), \
         patch("src.core.workflow.nodes.planner.get_llm_by_type", new=mock_factory), \
         patch("src.core.workflow.nodes.storywriter.get_llm_by_type", new=mock_factory), \
         patch("src.core.workflow.nodes.visualizer.get_llm_by_type", new=mock_factory), \
         patch("src.core.workflow.nodes.data_analyst.get_llm_by_type", new=mock_factory), \
         patch("src.core.workflow.nodes.researcher.get_llm_by_type", new=mock_factory):
        yield mock_factory

@pytest.mark.asyncio
async def test_full_graph_execution_happy_path(mock_get_llm):
    """
    Test the full happy path:
    Coordinator -> Planner -> Supervisor -> Storywriter -> Supervisor -> END
    """
    # 1. Setup Graph with Memory Checkpointer
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)

    # 2. Setup Mock LLM behaviors
    
    # Planner Output
    valid_plan = PlannerOutput(
        steps=[
            TaskStep(
                id=1, 
                role="storywriter", 
                instruction="Write story", 
                title="Story Creation",
                description="desc", 
                status="pending", 
                result_summary=None
            )
        ]
    )
    
    # Storywriter Output
    valid_story = StorywriterOutput(
        slides=[SlideContent(slide_number=1, title="Slide 1", bullet_points=["Point 1"], key_message="Key")],
        execution_summary="Created slides"
    )

    # Mock Decision for Coordinator
    coordinator_decision = CoordinatorDecision(
        decision="handoff_to_planner",
        response_content="Handoff confirmed."
    )
    
    planner_mock_llm = MagicMock()
    planner_mock_llm.invoke.return_value = valid_plan
    
    storywriter_mock_llm = MagicMock()
    storywriter_mock_llm.invoke.return_value = valid_story

    visualizer_mock_llm = MagicMock()
    visualizer_mock_llm.invoke.return_value = VisualizerOutput(prompts=[], execution_summary="done")

    data_analyst_mock_llm = MagicMock()
    data_analyst_mock_llm.invoke.return_value = DataAnalystOutput(
        analysis_report="Report", 
        execution_summary="done", 
        data_sources=[], 
        visualization_code=None
    )
    
    # Default/Fallback Mock
    default_mock = MagicMock()

    def get_llm_side_effect(llm_type):
        print(f"DEBUG: get_llm_side_effect called with {llm_type}")
        # Coordinator Uses "high_reasoning"
        if llm_type == "high_reasoning": 
            multi_purpose_llm = MagicMock()
            
            # For others (structured)
            def with_structured_side_effect(schema):
                print(f"DEBUG: with_structured_side_effect called with schema {schema}")
                struct_llm = MagicMock()
                if schema == VisualizerOutput:
                    struct_llm.invoke.return_value = VisualizerOutput(prompts=[], execution_summary="done")
                elif schema == DataAnalystOutput:
                     struct_llm.invoke.return_value = DataAnalystOutput(
                        analysis_report="Report", 
                        execution_summary="done",
                        data_sources=[]
                     )
                elif schema == CoordinatorDecision:
                    struct_llm.invoke.return_value = coordinator_decision
                # Fallback for other high_reasoning usages (like Planner if it uses high_reasoning?)
                # Actually Planner uses "high_reasoning" too in constants.py? "planner": "high_reasoning"
                # But in test code below: if llm_type == "reasoning": ...
                # Let's check constants.py again.
                elif schema == PlannerOutput:
                     struct_llm.invoke.return_value = valid_plan
                elif schema == StorywriterOutput:
                     struct_llm.invoke.return_value = valid_story
                
                return struct_llm
            
            multi_purpose_llm.with_structured_output.side_effect = with_structured_side_effect
            return multi_purpose_llm

        # Planner (Reasoning)
        if llm_type == "reasoning":
            print("DEBUG: Returning Planner Mock")
            planner_llm = MagicMock()
            planner_llm.with_structured_output.return_value = planner_mock_llm
            return planner_llm
            
        # Storywriter (Thinking)
        if llm_type == "gemini-2.0-flash-thinking-exp":
            print("DEBUG: Returning Storywriter Mock")
            story_llm = MagicMock()
            story_llm.with_structured_output.return_value = storywriter_mock_llm
            return story_llm
            
        return default_mock

    # Set side_effect on the FACTORY mock
    mock_get_llm.side_effect = get_llm_side_effect

    # 3. Run Graph
    initial_state = {
        "messages": [HumanMessage(content="Make slides about AI")],
        "plan": [],
        "artifacts": {}
    }
    
    config = {"configurable": {"thread_id": "integration_test_1"}}
    
    events = []
    # Print start
    print("DEBUG: Starting Graph Execution")
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        print(f"DEBUG: Event received keys: {event.keys() if isinstance(event, dict) else event}")
        events.append(event)
    print(f"DEBUG: Total events: {len(events)}")
        
    # 4. Assertions
    final_state = events[-1]
    import pprint
    print("DEBUG: Final State:")
    pprint.pprint(final_state)
    
    assert "plan" in final_state
    assert len(final_state["plan"]) > 0
    assert final_state["plan"][0]["status"] == "complete"
    assert "step_1_story" in final_state["artifacts"]
    assert json.loads(final_state["artifacts"]["step_1_story"])

@pytest.mark.asyncio
async def test_coordinator_direct_response(mock_get_llm):
    """
    Test: Coordinator decides NOT to use planner (Small Talk).
    START -> Coordinator -> END
    """
    checkpointer = MemorySaver()
    graph = build_graph(checkpointer=checkpointer)
    
    # Configure Factory to return a specific LLM
    mock_llm = MagicMock()
    # Mocking with_structured_output to return a mock that returns the decision
    mock_structured = MagicMock()
    # ainvoke must return an awaitable. We can use AsyncMock or set return_value to a future.
    # Easiest is to set ainvoke to an AsyncMock
    mock_structured.ainvoke = AsyncMock(return_value=CoordinatorDecision(
        decision="reply_to_user",
        reasoning="User just said Hi."
    ))
    mock_llm.with_structured_output.return_value = mock_structured
    
    # Mock astream to yield chunks for the streaming part
    async def mock_astream(*args, **kwargs):
        chunks = ["Hello", "!", " How", " can", " I", " help", "?"]
        for c in chunks:
            msg = AIMessage(content=c)
            # astream yields chunks which are messages or objects depending on model
            yield msg
            
    mock_llm.astream.side_effect = mock_astream
    
    mock_get_llm.side_effect = None
    mock_get_llm.return_value = mock_llm
    
    initial_state = {"messages": [HumanMessage(content="Hi")]}
    config = {"configurable": {"thread_id": "test_2"}}
    
    events = []
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        events.append(event)
        
    final_state = events[-1]
    
    assert not final_state.get("plan")
    assert final_state["messages"][-1].content == "Hello! How can I help?"
