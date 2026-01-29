import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import AIMessage
from src.core.workflow.nodes.coordinator import coordinator_node, CoordinatorDecision

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.coordinator.get_llm_by_type")
@patch("src.core.workflow.nodes.coordinator.adispatch_custom_event", new_callable=AsyncMock)
async def test_coordinator_node_handoff(mock_dispatch, mock_get_llm, empty_state):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    
    # Mock Structured Output
    mock_decision = CoordinatorDecision(decision="handoff_to_planner", response_content="Starting planning.")
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_decision
    
    # Execute node
    result = await coordinator_node(empty_state)
    
    # Verify results
    assert result.goto == "planner"
    assert "messages" in result.update
    assert result.update["messages"][0].content == "Starting planning."

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.coordinator.get_llm_by_type")
@patch("src.core.workflow.nodes.coordinator.adispatch_custom_event", new_callable=AsyncMock)
async def test_coordinator_node_end(mock_dispatch, mock_get_llm, empty_state):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    
    mock_decision = CoordinatorDecision(decision="reply_to_user", response_content="End of conversation.")
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_decision
    
    # Execute node
    result = await coordinator_node(empty_state)
    
    # Verify results
    assert result.goto == "__end__"
    assert result.update["messages"][0].content == "End of conversation."
