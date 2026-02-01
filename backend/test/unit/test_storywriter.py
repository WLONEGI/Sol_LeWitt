import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableConfig
from src.core.workflow.nodes.storywriter import storywriter_node
from src.shared.schemas import StorywriterOutput, SlideContent


@pytest.fixture
def mock_config():
    return RunnableConfig(configurable={"thread_id": "test-thread"})


@pytest.mark.asyncio
@patch("src.core.workflow.nodes.storywriter.get_llm_by_type")
@patch("src.core.workflow.nodes.storywriter.apply_prompt_template")
async def test_storywriter_node_success(mock_apply, mock_get_llm, empty_state, mock_config):
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
    
    # Mock ainvoke with response_format to return parsed output
    mock_llm.ainvoke = AsyncMock(return_value=mock_output)
    
    # Execute node
    result = await storywriter_node(state, mock_config)
    
    # Verify results - storywriter goes to supervisor via create_worker_response default
    assert result.goto == "supervisor"
    assert state["plan"][0]["result_summary"] == "Created 1 slide"
    
    # Verify ainvoke was called with response_format
    mock_llm.ainvoke.assert_called_once()
    call_kwargs = mock_llm.ainvoke.call_args[1]
    assert call_kwargs.get("response_format") == StorywriterOutput


@pytest.mark.asyncio
async def test_storywriter_node_no_step(empty_state, mock_config):
    # Execute node with no in_progress step
    result = await storywriter_node(empty_state, mock_config)
    
    assert result.goto == "supervisor"
    assert result.update == {}
