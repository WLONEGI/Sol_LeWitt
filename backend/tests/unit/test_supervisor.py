import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.core.workflow.nodes.supervisor import supervisor_node

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new_callable=AsyncMock)
@patch("src.core.workflow.nodes.supervisor.adispatch_custom_event", new_callable=AsyncMock)
async def test_supervisor_node_start(mock_dispatch, mock_report, empty_state):
    mock_report.return_value = "Starting step 1."
    # Setup state with pending steps
    state = empty_state.copy()
    state["plan"] = [
        {"id": 1, "role": "planner", "status": "pending", "title": "Plan"},
        {"id": 2, "role": "researcher", "status": "pending", "title": "Research"}
    ]
    
    # Execute node
    result = await supervisor_node(state)
    
    # Verify results
    assert result.goto == "planner"
    assert state["plan"][0]["status"] == "in_progress"

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new_callable=AsyncMock)
@patch("src.core.workflow.nodes.supervisor.adispatch_custom_event", new_callable=AsyncMock)
async def test_supervisor_node_next_step(mock_dispatch, mock_report, empty_state):
    mock_report.return_value = "Starting step 2."
    # Setup state with completed and pending steps
    state = empty_state.copy()
    state["plan"] = [
        {"id": 1, "role": "planner", "status": "completed", "title": "Plan"},
        {"id": 2, "role": "researcher", "status": "pending", "title": "Research"}
    ]
    
    # Execute node
    result = await supervisor_node(state)
    
    # Verify results
    assert result.goto == "researcher"
    assert state["plan"][1]["status"] == "in_progress"

@pytest.mark.asyncio
@patch("src.core.workflow.nodes.supervisor.adispatch_custom_event", new_callable=AsyncMock)
async def test_supervisor_node_end(mock_dispatch, empty_state):
    # Setup state with all steps completed
    state = empty_state.copy()
    state["plan"] = [
        {"id": 1, "role": "planner", "status": "completed", "title": "Plan"}
    ]
    
    # Execute node
    result = await supervisor_node(state)
    
    # Verify results
    assert result.goto == "__end__"
