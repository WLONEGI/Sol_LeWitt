import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from src.core.workflow.nodes.storywriter import storywriter_node
from src.shared.schemas import StorywriterOutput, SlideContent

@patch("src.core.workflow.nodes.storywriter.get_llm_by_type")
@patch("src.core.workflow.nodes.storywriter.apply_prompt_template")
def test_storywriter_node_success(mock_apply, mock_get_llm, empty_state):
    # Setup state with plan
    state = empty_state.copy()
    state["plan"] = [
        {
            "id": 1,
            "role": "storywriter",
            "instruction": "Write a story about AI",
            "status": "in_progress",
            "title": "Storytelling"
        }
    ]
    
    # Mock LLM and StorywriterOutput
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    
    mock_output = StorywriterOutput(
        execution_summary="Created 1 slide",
        slides=[
            SlideContent(
                slide_number=1,
                title="AI Growth",
                bullet_points=["Point 1", "Point 2"]
            )
        ]
    )
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_output
    
    # Execute node
    result = storywriter_node(state)
    
    # Verify results
    assert result.goto == "supervisor"
    assert state["plan"][0]["result_summary"] == "Created 1 slide"

def test_storywriter_node_no_step(empty_state):
    # Execute node with no in_progress step
    result = storywriter_node(empty_state)
    
    assert result.goto == "supervisor"
    assert result.update == {}
