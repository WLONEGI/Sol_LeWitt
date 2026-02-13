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

    assert cmd.goto == "planner"
    assert cmd.update["product_type"] == "comic"
    assert cmd.update["request_intent"] == "refine"
    assert "planning_mode" not in cmd.update
    assert cmd.update["interrupt_intent"] is False
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
        product_type="design",
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

    assert cmd.goto == "planner"
    assert cmd.update["product_type"] == "comic"


def test_coordinator_does_not_derive_update_mode_even_when_existing_plan_has_unfinished_steps() -> None:
    state = {
        "messages": [HumanMessage(content="3ページ目だけ修正して")],
        "plan": [
            {"id": 1, "capability": "writer", "status": "completed"},
            {"id": 2, "capability": "visualizer", "status": "in_progress"},
        ],
        "artifacts": {},
        "product_type": "comic",
    }
    output = CoordinatorOutput(
        product_type="comic",
        response="修正計画に更新します。",
        goto="planner",
        title="修正",
    )

    with patch("src.core.workflow.nodes.coordinator.get_llm_by_type", return_value=_LLMStub(output)), patch(
        "src.core.workflow.nodes.coordinator.apply_prompt_template",
        return_value=[HumanMessage(content="coordinator prompt")],
    ), patch(
        "src.core.workflow.nodes.coordinator._save_title",
        new=AsyncMock(return_value=None),
    ):
        cmd = asyncio.run(coordinator_node(state, {"configurable": {}}))

    assert cmd.goto == "planner"
    assert "planning_mode" not in cmd.update
    assert cmd.update["interrupt_intent"] is False
    assert cmd.update["target_scope"]["page_numbers"] == [3]


def test_coordinator_end_route_includes_three_followup_options() -> None:
    state = {
        "messages": [HumanMessage(content="まだ方向性が決まっていません")],
        "plan": [],
        "artifacts": {},
    }
    output = CoordinatorOutput(
        product_type="slide",
        response="方向性を明確にするため、まず目的を確認させてください。",
        goto="__end__",
        title=None,
        followup_options=[
            {
                "prompt": "まずは目的を整理したいです。成果のゴールは〇〇です。",
            }
        ],
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
    options = cmd.update.get("coordinator_followup_options")
    assert isinstance(options, list)
    assert len(options) == 3
    assert all("prompt" in option for option in options)
