import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from src.core.workflow.nodes.planner import planner_node
from src.shared.schemas import PlannerOutput, TaskStep


@pytest.fixture
def mock_config():
    return RunnableConfig(configurable={"thread_id": "test-thread"})


@pytest.mark.asyncio
@patch("src.core.workflow.nodes.planner.get_llm_by_type")
@patch("src.core.workflow.nodes.planner.apply_prompt_template")
async def test_planner_node_success(mock_apply, mock_get_llm, empty_state, mock_config):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    
    # Mock PlannerOutput
    mock_output = PlannerOutput(
        steps=[
            TaskStep(
                id=1,
                role="researcher",
                instruction="Research AI trends",
                title="Research",
                description="AI Trends research",
                status="pending"
            )
        ]
    )
    
    # Mock ainvoke with response_format to return parsed output
    mock_llm.ainvoke = AsyncMock(return_value=mock_output)
    
    # Execute node
    result = await planner_node(empty_state, mock_config)
    
    # Verify results
    assert result.goto == "supervisor"
    assert "plan" in result.update
    assert len(result.update["plan"]) == 1
    
    # Verify ainvoke was called with response_format
    mock_llm.ainvoke.assert_called_once()
    call_kwargs = mock_llm.ainvoke.call_args[1]
    assert call_kwargs.get("response_format") == PlannerOutput


@pytest.mark.asyncio
@patch("src.core.workflow.nodes.planner.get_llm_by_type")
@patch("src.core.workflow.nodes.planner.apply_prompt_template")
async def test_planner_node_failure(mock_apply, mock_get_llm, empty_state, mock_config):
    # Setup mock LLM to raise exception
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    
    # Mock ainvoke to raise exception
    mock_llm.ainvoke = AsyncMock(side_effect=ValueError("Parse failure"))
    
    # Execute node
    result = await planner_node(empty_state, mock_config)
    
    # Verify fallback to __end__
    assert result.goto == "__end__"
