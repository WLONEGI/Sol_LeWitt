import pytest
import unittest.mock as mock
from typing import Any
from langchain_core.messages import HumanMessage, AIMessage
from src.core.workflow.state import State

@pytest.fixture
def mock_llm():
    llm = mock.MagicMock()
    # default side effect for structured output
    llm.with_structured_output.return_value = llm
    return llm

@pytest.fixture
def empty_state() -> State:
    return {
        "messages": [],
        "plan": [],
        "artifacts": {},
        "design_context": None
    }

@pytest.fixture
def mock_get_llm():
    with mock.patch("src.infrastructure.llm.llm.get_llm_by_type") as mocked:
        yield mocked

@pytest.fixture
def mock_apply_prompt():
    with mock.patch("src.resources.prompts.template.apply_prompt_template") as mocked:
        mocked.return_value = [HumanMessage(content="test prompt")]
        yield mocked

@pytest.fixture
def mock_llm_response():
    def _create_mock(content, tool_calls=None):
        return AIMessage(content=content, tool_calls=tool_calls or [])
    return _create_mock

@pytest.fixture(autouse=True)
def mock_settings():
    """Ensure settings are mocked for all tests to prevent env var dependency."""
    with mock.patch("src.shared.config.settings.settings") as mock_settings:
        # Default values for tests
        mock_settings.RESPONSE_FORMAT = "Role: {role}\nContent: {content}"
        mock_settings.AGENT_LLM_MAP = {
            "coordinator": "gemini-2.0-flash-exp",
            "planner": "reasoning",
            "storywriter": "gemini-2.0-flash-thinking-exp",
            "visualizer": "gemini-2.0-flash-exp",
            "data_analyst": "gemini-2.0-flash-exp"
        }
        yield mock_settings
