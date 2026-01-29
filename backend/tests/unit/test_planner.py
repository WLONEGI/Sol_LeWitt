import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage
from src.core.workflow.nodes.planner import planner_node
from src.shared.schemas import PlannerOutput, TaskStep

@patch("src.core.workflow.nodes.planner.get_llm_by_type")
@patch("src.core.workflow.nodes.planner.apply_prompt_template")
def test_planner_node_success(mock_apply, mock_get_llm, empty_state):
    # Setup mock structured LLM
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
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_output
    
    # Execute node
    result = planner_node(empty_state)
    
    # Verify results
    assert result.goto == "supervisor"
    assert "plan" in result.update
    assert len(result.update["plan"]) == 1
    
@patch("src.core.workflow.nodes.planner.get_llm_by_type")
@patch("src.core.workflow.nodes.planner.apply_prompt_template")
def test_planner_node_failure(mock_apply, mock_get_llm, empty_state):
    # Setup mock structured LLM to raise exception
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    mock_llm.with_structured_output.return_value.invoke.side_effect = Exception("LLM Error")
    
    # Execute node
    result = planner_node(empty_state)
    
    # Verify fallback to __end__
    assert result.goto == "__end__"
