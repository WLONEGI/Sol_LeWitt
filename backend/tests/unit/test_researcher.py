import pytest
from unittest.mock import MagicMock, patch
from langchain_core.messages import AIMessage
from src.core.workflow.nodes.researcher import research_worker_node, research_manager_node
from src.shared.schemas import ResearchTaskList, ResearchTask, ResearchResult

@patch("src.core.workflow.nodes.researcher.get_llm_by_type")
@patch("src.core.workflow.nodes.researcher.load_prompt_markdown")
def test_research_worker_node_success(mock_load, mock_get_llm):
    # Setup state
    task = ResearchTask(id=1, perspective="test", query_hints=[], priority="medium", expected_output="report")
    state = {"task": task}
    
    # Mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_load.return_value = "system prompt"
    
    mock_response = AIMessage(content="Research result content")
    mock_llm.bind.return_value.invoke.return_value = mock_response
    
    # Execute node
    result = research_worker_node(state)
    
    # Verify
    assert "internal_research_results" in result
    assert result["internal_research_results"][0].report == "Research result content"

@patch("src.core.workflow.nodes.researcher.get_llm_by_type")
@patch("src.core.workflow.nodes.researcher.load_prompt_markdown")
def test_research_manager_node_decomposition(mock_load, mock_get_llm):
    # Setup state
    state = {
        "plan": [{"id": 1, "role": "researcher", "status": "in_progress", "instruction": "research AI", "title": "step1"}],
        "is_decomposed": False,
        "internal_research_tasks": [],
        "internal_research_results": []
    }
    
    # Mock LLM
    mock_llm = MagicMock()
    mock_get_llm.return_value = mock_llm
    mock_load.return_value = "system prompt"
    
    mock_output = ResearchTaskList(tasks=[
        ResearchTask(id=1, perspective="p1", query_hints=[], priority="medium", expected_output="o1")
    ])
    mock_llm.with_structured_output.return_value.invoke.return_value = mock_output
    
    # Execute
    result = research_manager_node(state)
    
    # Verify Send commands
    assert any(cmd.node == "research_worker" for cmd in result.goto)
    assert result.update["is_decomposed"] == True

def test_research_manager_node_aggregation():
    # Setup state with completed tasks
    task = ResearchTask(id=1, perspective="p1", query_hints=[], priority="medium", expected_output="o1")
    state = {
        "plan": [{"id": 1, "role": "researcher", "status": "in_progress", "instruction": "research AI", "title": "step1"}],
        "is_decomposed": True,
        "internal_research_tasks": [task],
        "internal_research_results": [ResearchResult(task_id=1, perspective="p1", report="r1", sources=[], confidence=1.0)],
        "artifacts": {}
    }
    
    # Execute
    result = research_manager_node(state)
    
    # Verify
    assert result.goto == "supervisor"
    assert "step_1_research" in result.update["artifacts"]
    assert state["plan"][0]["result_summary"] == "以下の項目について詳細に調査し、分析レポートを作成しました: p1"
