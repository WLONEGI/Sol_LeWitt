import asyncio
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from src.core.workflow.nodes.coordinator import CoordinatorOutput, coordinator_node


class _StructuredLLMStub:
    def __init__(self, output: CoordinatorOutput):
        self._output = output

    async def ainvoke(self, _messages, config=None):
        return self._output


class _LLMStub:
    def __init__(self, output: CoordinatorOutput):
        self._output = output

    def with_structured_output(self, _schema):
        return _StructuredLLMStub(self._output)


def test_coordinator_routes_unsupported_category_to_end() -> None:
    state = {
        "messages": [HumanMessage(content="動画を作って")],
        "plan": [],
        "artifacts": {},
    }
    output = CoordinatorOutput(
        product_type="unsupported",
        response="動画は対象外です。対応カテゴリをご指定ください。",
        goto="planner",
        title=None,
    )

    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", return_value=_LLMStub(output)), patch(
        "src.core.workflow.nodes.coordinator.apply_prompt_template",
        return_value=[HumanMessage(content="coordinator prompt")],
    ), patch(
        "src.core.workflow.nodes.coordinator._save_title",
        new=AsyncMock(return_value=None),
    ):
        cmd = asyncio.run(coordinator_node(state, {"configurable": {}}))

    assert cmd.goto == "__end__"
    assert "product_type" not in cmd.update


def test_coordinator_sets_product_intent_and_scope_for_supported_category() -> None:
    state = {
        "messages": [HumanMessage(content="漫画の3ページを修正して")],
        "plan": [],
        "artifacts": {},
    }
    output = CoordinatorOutput(
        product_type="comic",
        response="承知しました。漫画制作を開始します。",
        goto="planner",
        title="漫画修正",
    )

    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", return_value=_LLMStub(output)), patch(
        "src.core.workflow.nodes.coordinator.apply_prompt_template",
        return_value=[HumanMessage(content="coordinator prompt")],
    ), patch(
        "src.core.workflow.nodes.coordinator._save_title",
        new=AsyncMock(return_value=None),
    ):
        cmd = asyncio.run(coordinator_node(state, {"configurable": {}}))

    assert cmd.goto == "plan_manager"
    assert cmd.update["product_type"] == "comic"
    assert cmd.update["request_intent"] == "refine"
    assert cmd.update["target_scope"]["page_numbers"] == [3]
    assert cmd.update["target_scope"]["asset_unit_ids"] == ["page:3"]


def test_coordinator_keeps_existing_product_type_locked() -> None:
    state = {
        "messages": [HumanMessage(content="次は雑誌デザインにして")],
        "plan": [],
        "artifacts": {},
        "product_type": "comic",
    }
    output = CoordinatorOutput(
        product_type="document_design",
        response="承知しました。制作を続行します。",
        goto="planner",
        title="制作続行",
    )

    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", return_value=_LLMStub(output)), patch(
        "src.core.workflow.nodes.coordinator.apply_prompt_template",
        return_value=[HumanMessage(content="coordinator prompt")],
    ), patch(
        "src.core.workflow.nodes.coordinator._save_title",
        new=AsyncMock(return_value=None),
    ):
        cmd = asyncio.run(coordinator_node(state, {"configurable": {}}))

    assert cmd.goto == "plan_manager"
    assert cmd.update["product_type"] == "comic"
