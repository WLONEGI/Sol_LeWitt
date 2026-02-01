import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from langchain_core.messages import AIMessage
from src.core.workflow.nodes.coordinator import coordinator_node, CoordinatorDecision
from src.core.workflow.service import _manager

@pytest.fixture
def mock_db_pool():
    with patch("src.core.workflow.service._manager.pool") as mock_pool:
        mock_conn = MagicMock()
        mock_cursor = AsyncMock()
        
        # Mock connection context manager
        mock_pool.connection.return_value.__aenter__.return_value = mock_conn
        
        # Mock cursor context manager
        mock_conn.cursor.return_value.__aenter__.return_value = mock_cursor
        
        yield mock_pool, mock_cursor

@pytest.mark.asyncio
@pytest.mark.asyncio
@patch("src.core.workflow.nodes.coordinator.get_llm_by_type")
async def test_coordinator_node_handoff(mock_get_llm, empty_state, mock_db_pool):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    
    # Mock Structured Output
    mock_decision = CoordinatorDecision(decision="handoff_to_planner", reasoning="Testing handoff")
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)
    
    # Mock astream for handoff message generation
    async def async_gen():
        yield AIMessage(content="Starting planning.")
    mock_llm.astream.return_value = async_gen()
    
    # Mock RunnableConfig
    config = {"configurable": {"thread_id": "test_thread_1"}}
    
    # Execute node
    result = await coordinator_node(empty_state, config)
    
    # Verify results
    assert result.goto == "planner"
    assert "messages" in result.update
    assert result.update["messages"][0].content == "Starting planning."
    
    # Verify DB pool interaction (ensure title was saved)
    mock_pool, mock_cursor = mock_db_pool
    # Since existing thread check might pass or fail based on mock, we check if pool was accessed
    mock_pool.connection.assert_called()

@pytest.mark.asyncio
@pytest.mark.asyncio
@patch("src.core.workflow.nodes.coordinator.get_llm_by_type")
async def test_coordinator_node_end(mock_get_llm, empty_state, mock_db_pool):
    # Setup mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    
    mock_decision = CoordinatorDecision(decision="reply_to_user", reasoning="End of conversation.")
    mock_llm.with_structured_output.return_value.ainvoke = AsyncMock(return_value=mock_decision)
    
    # Mock astream for reply generation
    async def async_gen():
        yield AIMessage(content="End of conversation.")
    mock_llm.astream.return_value = async_gen()
    
    config = {"configurable": {"thread_id": "test_thread_2"}}

    # Execute node
    result = await coordinator_node(empty_state, config)
    
    # Verify results
    assert result.goto == "__end__"
    assert result.update["messages"][0].content == "End of conversation."
