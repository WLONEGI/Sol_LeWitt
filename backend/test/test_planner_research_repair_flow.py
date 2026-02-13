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


def test_planner_allows_plan_when_research_is_required_but_not_explicit_in_hybrid_mode():
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

    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["capability"] == "writer"
    assert mock_structured_output.await_count == 0


def test_planner_ends_when_product_type_is_missing():
    state = {
        "messages": [HumanMessage(content="スライドを作成して")],
        "plan": [],
        "artifacts": {},
    }

    cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "__end__"
    assert "プロダクト種別が未確定" in cmd.update["messages"][0].content


def test_planner_update_mode_preserves_completed_steps_and_merges_pending_changes():
    state = {
        "messages": [HumanMessage(content="3枚目の画像を差し替えて")],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "既存アウトラインを維持する",
                "title": "構成作成",
                "description": "構成作成",
                "status": "completed",
            },
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "全スライド画像を生成する",
                "title": "画像生成",
                "description": "画像生成",
                "status": "pending",
            },
        ],
        "artifacts": {"step_1_story": "{\"execution_summary\":\"ok\"}"},
        "product_type": "slide",
        "request_intent": "refine",
        "planning_mode": "update",
        "target_scope": {"slide_numbers": [3], "asset_unit_ids": ["slide:3"]},
    }

    streamed = {
        "steps": [
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "3枚目のみ再生成する",
                "title": "画像修正",
                "description": "対象スライドのみ再生成",
                "inputs": ["outline"],
                "outputs": ["slides:images"],
                "preconditions": ["構成が存在する"],
                "validation": ["3枚目のみ更新される"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [1],
                "status": "pending",
            },
            {
                "id": 99,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "差し替え理由を注記する",
                "title": "注記追加",
                "description": "注記を追加",
                "inputs": ["slides:images"],
                "outputs": ["note"],
                "preconditions": [],
                "validation": ["注記が存在する"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [2],
                "status": "pending",
            },
        ]
    }
    streaming_llm = _StreamingLLM(json.dumps(streamed, ensure_ascii=False))

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ):
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "supervisor"
    assert cmd.update["planning_mode"] == "create"
    assert cmd.update["artifacts"] == {}

    plan = cmd.update["plan"]
    assert len(plan) == 2
    assert plan[0]["id"] == 2
    assert plan[0]["instruction"] == "3枚目のみ再生成する"
    assert plan[0]["status"] == "pending"
    assert plan[1]["id"] == 99


def test_planner_create_mode_resets_artifacts():
    state = {
        "messages": [HumanMessage(content="新しい提案資料を作って")],
        "plan": [],
        "artifacts": {"legacy": "keep"},
        "product_type": "slide",
        "request_intent": "new",
        "planning_mode": "create",
    }

    streamed = {
        "steps": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "新規アウトラインを作成する",
                "title": "アウトライン",
                "description": "アウトライン作成",
                "inputs": ["user_request"],
                "outputs": ["outline"],
                "preconditions": [],
                "validation": ["構成が作成される"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [],
                "status": "pending",
            }
        ]
    }
    streaming_llm = _StreamingLLM(json.dumps(streamed, ensure_ascii=False))

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ):
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "supervisor"
    assert cmd.update["planning_mode"] == "create"
    assert cmd.update["artifacts"] == {}


def test_planner_interrupt_intent_forces_update_mode():
    state = {
        "messages": [HumanMessage(content="この方針で新規に作成して")],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "下書きを作る",
                "title": "下書き",
                "description": "下書き",
                "status": "in_progress",
            }
        ],
        "artifacts": {"step_1_story": "{\"execution_summary\":\"working\"}"},
        "product_type": "slide",
        "request_intent": "new",
        "interrupt_intent": True,
    }

    streamed = {
        "steps": [
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "既存下書きをもとに画像化する",
                "title": "画像化",
                "description": "画像化",
                "inputs": ["outline"],
                "outputs": ["slides:images"],
                "preconditions": [],
                "validation": ["出力される"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [1],
                "status": "pending",
            }
        ]
    }
    streaming_llm = _StreamingLLM(json.dumps(streamed, ensure_ascii=False))

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ):
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "supervisor"
    assert cmd.update["planning_mode"] == "create"
    assert cmd.update["artifacts"] == {}


def test_planner_update_mode_does_not_replace_in_progress_step_directly():
    state = {
        "messages": [HumanMessage(content="2枚目の画像だけ雰囲気を変えて")],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "構成を確定する",
                "title": "構成確定",
                "description": "構成確定",
                "status": "completed",
            },
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "全スライド画像を生成する",
                "title": "画像生成",
                "description": "画像生成",
                "status": "in_progress",
                "depends_on": [1],
            },
        ],
        "artifacts": {},
        "product_type": "slide",
        "request_intent": "refine",
        "planning_mode": "update",
        "target_scope": {"slide_numbers": [2], "asset_unit_ids": ["slide:2"]},
    }

    streamed = {
        "steps": [
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "2枚目だけ再生成する",
                "title": "画像差し替え",
                "description": "2枚目のみ再生成",
                "inputs": ["outline"],
                "outputs": ["slides:images"],
                "preconditions": [],
                "validation": ["2枚目のみ変更される"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [1],
                "status": "pending",
            }
        ]
    }
    streaming_llm = _StreamingLLM(json.dumps(streamed, ensure_ascii=False))

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ):
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "supervisor"
    plan = cmd.update["plan"]

    assert len(plan) == 1
    assert plan[0]["id"] == 2
    assert plan[0]["instruction"] == "2枚目だけ再生成する"
    assert plan[0]["status"] == "pending"


def test_planner_update_mode_sanitizes_self_and_invalid_dependencies():
    state = {
        "messages": [HumanMessage(content="図版を追加して")],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "instruction": "構成を作成する",
                "title": "構成作成",
                "description": "構成作成",
                "status": "completed",
            }
        ],
        "artifacts": {},
        "product_type": "slide",
        "request_intent": "refine",
        "planning_mode": "update",
    }

    streamed = {
        "steps": [
            {
                "id": 99,
                "capability": "visualizer",
                "mode": "slide_render",
                "instruction": "図版を1枚追加する",
                "title": "図版追加",
                "description": "図版追加",
                "inputs": ["outline"],
                "outputs": ["slides:images"],
                "preconditions": [],
                "validation": ["図版が追加される"],
                "fallback": ["retry_with_tighter_constraints"],
                "depends_on": [99, 1, 999],
                "status": "pending",
            }
        ]
    }
    streaming_llm = _StreamingLLM(json.dumps(streamed, ensure_ascii=False))

    with patch("src.core.workflow.nodes.planner.get_llm_by_type", return_value=streaming_llm), patch(
        "src.core.workflow.nodes.planner.apply_prompt_template",
        return_value=[HumanMessage(content="planner prompt")],
    ), patch(
        "src.core.workflow.nodes.planner.run_structured_output",
        new=AsyncMock(),
    ):
        cmd = asyncio.run(planner_node(state, {}))

    assert cmd.goto == "supervisor"
    added_step = cmd.update["plan"][0]
    assert added_step["depends_on"] == [99, 1, 999]
