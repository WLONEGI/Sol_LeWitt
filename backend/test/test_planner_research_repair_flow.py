import asyncio
import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from src.core.workflow.nodes.planner import planner_node


class _Chunk:
    def __init__(self, content: str):
        self.content = content


class _StreamingLLM:
    def __init__(self, streamed_text: str):
        self._streamed_text = streamed_text

    async def astream(self, _messages, config=None):
        yield _Chunk(self._streamed_text)


def _planner_output_json_without_research() -> str:
    payload = {
        "steps": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "出典付きで構成を作る",
                "title": "構成作成",
                "description": "構成作成",
                "inputs": ["user_request"],
                "outputs": ["outline"],
                "preconditions": ["none"],
                "validation": ["出典要件を満たす"],
                "fallback": ["researcherに確認"],
                "depends_on": [],
            }
        ]
    }
    return json.dumps(payload, ensure_ascii=False)


def test_planner_rejects_plan_when_research_is_required_but_not_explicit():
    state = {
        "messages": [HumanMessage(content="中世情報の出典を明示して漫画化して")],
        "plan": [],
        "artifacts": {},
        "product_type": "comic",
    }

    streaming_llm = _StreamingLLM(_planner_output_json_without_research())

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ) as mock_structured_output:
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "__end__"
    assert "明示的なResearcherステップ" in cmd.update["messages"][0].content
    assert mock_structured_output.await_count == 0
