import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage
from src.core.workflow.nodes.data_analyst import data_analyst_node
from src.shared.schemas import DataAnalystOutput

@patch("src.core.workflow.nodes.data_analyst.get_llm_by_type")
@patch("src.core.workflow.nodes.data_analyst.apply_prompt_template")
def test_data_analyst_node_success(mock_apply, mock_get_llm, empty_state):
    # Setup state
    state = empty_state.copy()
    state["plan"] = [
        {"id": 1, "role": "data_analyst", "status": "in_progress", "instruction": "Analyze data"}
    ]
    
    # Mock LLM and response
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    
    # Mock LLM response with JSON content
    mock_output = DataAnalystOutput(
        blueprints=[],
        execution_summary="Analyzed 10 rows",
        analysis_report="The data shows growth.",
        data_sources=["Source A"]
    )
    mock_response = AIMessage(content=f"```json\n{mock_output.model_dump_json()}\n```")
    mock_llm.bind_tools.return_value.invoke.return_value = mock_response
    
    # Execute node
    mock_config = MagicMock()
    result = data_analyst_node(state, config=mock_config)
    
    # Verify results
    assert result.goto == "supervisor"
    assert state["plan"][0]["result_summary"] == "Analyzed 10 rows"

@patch("src.core.workflow.nodes.data_analyst.get_llm_by_type")
@patch("src.core.workflow.nodes.data_analyst.apply_prompt_template")
def test_data_analyst_node_failure(mock_apply, mock_get_llm, empty_state):
    # Setup state
    state = empty_state.copy()
    state["plan"] = [
        {"id": 1, "role": "data_analyst", "status": "in_progress", "instruction": "Analyze data"}
    ]
    
    # Mock LLM failure
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_apply.return_value = [HumanMessage(content="test prompt")]
    mock_llm.bind_tools.return_value.invoke.side_effect = Exception("Analysis error")
    
    # Execute node
    mock_config = MagicMock()
    result = data_analyst_node(state, config=mock_config)
    
    # Verify results - should still go to supervisor but with error summary
    assert result.goto == "supervisor"
    assert "Error: Analysis error" in state["plan"][0]["result_summary"]
