import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage
from src.core.workflow.nodes.visualizer import visualizer_node
from src.shared.schemas import VisualizerOutput, ImagePrompt, ThoughtSignature

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.visualizer.get_llm_by_type")
async def test_visualizer_node_success(mock_get_llm, empty_state):
    # Setup state with plan
    state = empty_state.copy()
    state["plan"] = [
        {
            "id": 2,
            "role": "visualizer",
            "instruction": "Generate AI images",
            "status": "in_progress",
            "title": "Visualization"
        }
    ]
    
    # Mock LLM and VisualizerOutput
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    
    mock_output = VisualizerOutput(
        execution_summary="Generated 1 image",
        prompts=[
            ImagePrompt(
                slide_number=1,
                layout_type="title_slide",
                image_generation_prompt="AI robot",
                rationale="Visual representation of AI",
                generated_image_url="http://gcs/image.png"
            )
        ]
    )
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_output
    
    # Mock external calls
    with patch("src.core.workflow.nodes.visualizer.create_image_chat_session_async", new_callable=AsyncMock) as mock_chat, \
         patch("src.core.workflow.nodes.visualizer.process_slide_with_chat", new_callable=AsyncMock) as mock_process:
        
        mock_processed_prompt = mock_output.prompts[0].model_copy()
        mock_process.return_value = mock_processed_prompt
        
        # Execute node
        result = await visualizer_node(state)
        
        # Verify results
        assert result.goto == "supervisor"
        assert state["plan"][0]["result_summary"] == "Generated 1 image"
