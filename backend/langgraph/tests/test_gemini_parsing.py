
import asyncio
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from src.graph.nodes import storywriter_node, visualizer_node, data_analyst_node
from src.schemas.outputs import StorywriterOutput, VisualizerOutput, DataAnalystOutput, SlideContent, ImagePrompt, VisualBlueprint
from src.graph.graph_types import State

# Simple fixture replacement
def get_mock_state():
    return State(
        current_step_index=0,
        plan=[
            {"id": 1, "role": "storywriter", "instruction": "Write a story about AI", "description": "desc", "title": "title", "dependencies": []}
        ],
        artifacts={},
        messages=[],
        design_context=None
    )

async def test_storywriter_node_parsing(mock_state):
    """Verify Storywriter node correctly parses Gemini response using with_structured_output"""
    
    # Mock LLM and structured_llm
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    
    # Setup mock response
    expected_output = StorywriterOutput(
        slides=[
            SlideContent(slide_number=1, title="Intro", bullet_points=["Bullet 1"])
        ]
    )
    mock_structured_llm.invoke.return_value = expected_output
    
    # Mock dependencies
    with patch("src.graph.nodes.get_llm_by_type", return_value=mock_llm) as mock_get_llm:
        # Mock with_structured_output to return our mock_structured_llm
        mock_llm.with_structured_output.return_value = mock_structured_llm
        
        # Execute node
        result = storywriter_node(mock_state)
        
        # Verify interactions
        assert result.goto == "reviewer"
        mock_llm.with_structured_output.assert_called_once_with(StorywriterOutput)
        mock_structured_llm.invoke.assert_called_once()
        print("✅ Storywriter Node parsing verified")

async def test_visualizer_node_parsing(mock_state):
    """Verify Visualizer node correctly parses Gemini response using with_structured_output"""
    
    mock_state["plan"][0]["role"] = "visualizer"
    
    # Mock LLM and structured_llm
    mock_llm = MagicMock()
    mock_structured_llm = MagicMock()
    
    # Setup mock response
    expected_output = VisualizerOutput(
        prompts=[
            ImagePrompt(slide_number=1, image_generation_prompt="A robot painting", rationale="Creative AI")
        ]
    )
    mock_structured_llm.invoke.return_value = expected_output
    

    # Mock dependencies
    with patch("src.graph.nodes.get_llm_by_type", return_value=mock_llm) as mock_get_llm:
        mock_llm.with_structured_output.return_value = mock_structured_llm
        
        # Mock process_single_slide (async)
        async def mock_process_side_effect(prompt_item, *args, **kwargs):
             # Emulate return of updated prompt item
             prompt_item.generated_image_url = "gs://mock/url"
             return prompt_item
             
        with patch("src.graph.nodes.process_single_slide", side_effect=mock_process_side_effect):
             # Also mock download_blob_as_bytes to avoid network calls
             with patch("src.graph.nodes.download_blob_as_bytes", return_value=b"fake_image_bytes"):
                 result = await visualizer_node(mock_state)
        
        assert result.goto == "reviewer"
        mock_llm.with_structured_output.assert_called_once_with(VisualizerOutput)
        print("✅ Visualizer Node parsing verified")

def test_data_analyst_node_parsing(mock_state):
    """Verify Data Analyst configuration"""
    mock_state["plan"][0]["role"] = "data_analyst"
    
     # Mock LLM
    mock_llm = MagicMock()
    mock_bound_llm = MagicMock()
    
    # Mock response content (JSON string)
    mock_response = MagicMock()
    mock_response.content = '{"blueprints": [], "design_notes": "None"}'
    mock_bound_llm.invoke.return_value = mock_response
    
    with patch("src.graph.nodes.get_llm_by_type", return_value=mock_llm):
        mock_llm.bind.return_value = mock_bound_llm
        
        result = data_analyst_node(mock_state)
        
        # Verify bind called with tools (checking the fix)
        args, kwargs = mock_llm.bind.call_args
        assert "tools" in kwargs
        assert kwargs["tools"] == [{"code_execution": {}}]
        print("✅ Data Analyst tools binding verified")

if __name__ == "__main__":
    import asyncio
    
    # Manual run wrapper
    mock_state_obj = State(
        current_step_index=0,
        plan=[
            {"id": 1, "role": "storywriter", "instruction": "Write a story about AI", "description": "desc", "title": "title", "dependencies": []}
        ],
        artifacts={},
        messages=[],
        design_context=None
    )
    
    print("Running tests manually...")
    asyncio.run(test_storywriter_node_parsing(mock_state_obj))
    asyncio.run(test_visualizer_node_parsing(mock_state_obj))
    test_data_analyst_node_parsing(mock_state_obj)
    print("ALL TESTS PASSED")
