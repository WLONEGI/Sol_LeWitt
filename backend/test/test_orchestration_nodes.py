import asyncio
import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from src.core.workflow.nodes.orchestration import (
    patch_gate_node,
    patch_planner_node,
    plan_manager_node,
    retry_or_alt_mode_node,
)
from src.core.workflow.nodes.supervisor import supervisor_node


def test_plan_manager_routes_initial_turn_to_planner() -> None:
    state = {
        "messages": [HumanMessage(content="漫画を作って")],
        "plan": [],
        "artifacts": {},
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "planner"
    assert cmd.update["plan_status"] == "frozen"
    assert cmd.update["rethink_used_turn"] == 0


def test_plan_manager_normalizes_step_shape_to_v2() -> None:
    state = {
        "messages": [HumanMessage(content="続けて")],
        "plan": [
            {
                "id": 1,
                "status": "pending",
                "capability": "writer",
                "instruction": "構成を作る",
                "description": "構成作成",
            }
        ],
        "artifacts": {},
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "supervisor"
    normalized_plan = cmd.update["plan"]
    assert "role" not in normalized_plan[0]
    assert normalized_plan[0]["capability"] == "writer"
    assert normalized_plan[0]["instruction"] == "構成を作る"


def test_plan_manager_routes_existing_plan_to_patch_gate_when_patch_exists() -> None:
    state = {
        "messages": [HumanMessage(content="2コマ目だけ修正")],
        "plan": [{"id": 1, "status": "pending", "capability": "writer"}],
        "artifacts": {},
        "plan_patch_log": [{"op": "edit_pending", "target_step_id": 1, "payload": {"instruction": "x"}}],
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "patch_gate"
    assert isinstance(cmd.update["plan_baseline_hash"], str)


def test_plan_manager_routes_refine_to_patch_planner() -> None:
    state = {
        "messages": [HumanMessage(content="2枚目の色調だけ修正して")],
        "plan": [{"id": 1, "status": "pending", "capability": "visualizer"}],
        "artifacts": {},
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "patch_planner"
    assert cmd.update["request_intent"] == "refine"


def test_plan_manager_routes_regenerate_to_patch_planner() -> None:
    state = {
        "messages": [HumanMessage(content="2枚目を再生成して")],
        "plan": [{"id": 1, "status": "pending", "capability": "visualizer"}],
        "artifacts": {},
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "patch_planner"
    assert cmd.update["request_intent"] == "regenerate"


def test_plan_manager_treats_interrupt_new_intent_as_refine() -> None:
    state = {
        "messages": [HumanMessage(content="あと余白を少し調整したい")],
        "plan": [{"id": 1, "status": "pending", "capability": "visualizer"}],
        "artifacts": {},
        "interrupt_intent": True,
    }
    cmd = asyncio.run(plan_manager_node(state, {}))
    assert cmd.goto == "patch_planner"
    assert cmd.update["request_intent"] == "refine"
    assert cmd.update["interrupt_intent"] is True


def test_patch_gate_applies_edit_pending() -> None:
    state = {
        "messages": [],
        "plan": [
            {"id": 1, "status": "pending", "capability": "writer", "instruction": "old", "description": "d1"},
            {"id": 2, "status": "completed", "capability": "visualizer", "instruction": "done", "description": "d2"},
        ],
        "artifacts": {},
        "plan_patch_log": [{"op": "edit_pending", "target_step_id": 1, "payload": {"instruction": "new"}}],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["instruction"] == "new"
    assert cmd.update["plan_patch_log"] == []


def test_patch_gate_applies_edit_on_canonical_step() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "status": "pending",
                "capability": "writer",
                "instruction": "old",
                "description": "d1",
            }
        ],
        "artifacts": {},
        "plan_patch_log": [{"op": "edit_pending", "target_step_id": 1, "payload": {"instruction": "new"}}],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    updated = cmd.update["plan"][0]
    assert updated["instruction"] == "new"
    assert "role" not in updated
    assert updated["capability"] == "writer"


def test_patch_planner_generates_edit_pending_for_pending_step() -> None:
    state = {
        "messages": [HumanMessage(content="2枚目の色調を暖色に修正して")],
        "request_intent": "refine",
        "product_type": "slide_infographic",
        "plan": [
            {
                "id": 1,
                "status": "pending",
                "capability": "visualizer",
                "instruction": "既存画像を生成",
                "title": "Visual",
                "description": "Visual step",
            }
        ],
        "artifacts": {},
    }
    cmd = asyncio.run(patch_planner_node(state, {}))
    assert cmd.goto == "patch_gate"
    op = cmd.update["plan_patch_log"][0]
    assert op["op"] == "edit_pending"
    assert op["target_step_id"] == 1
    assert "暖色" in op["payload"]["instruction"]
    assert op["payload"]["target_scope"]["slide_numbers"] == [2]
    assert op["payload"]["target_scope"]["asset_unit_ids"] == ["slide:2"]


def test_patch_planner_generates_append_tail_when_no_pending_target() -> None:
    state = {
        "messages": [HumanMessage(content="画像の色を落ち着いたトーンに直して")],
        "request_intent": "refine",
        "product_type": "slide_infographic",
        "plan": [
            {
                "id": 1,
                "status": "completed",
                "capability": "visualizer",
            }
        ],
        "artifacts": {},
    }
    cmd = asyncio.run(patch_planner_node(state, {}))
    assert cmd.goto == "patch_gate"
    op = cmd.update["plan_patch_log"][0]
    assert op["op"] == "append_tail"
    steps = op["payload"]["steps"]
    assert steps[0]["capability"] == "visualizer"
    assert steps[1]["capability"] == "data_analyst"


def test_patch_planner_regenerate_forces_append_tail_even_with_pending_step() -> None:
    state = {
        "messages": [HumanMessage(content="2枚目を再生成して")],
        "request_intent": "regenerate",
        "product_type": "slide_infographic",
        "plan": [
            {
                "id": 1,
                "status": "pending",
                "capability": "visualizer",
                "instruction": "既存画像を生成",
                "title": "Visual",
                "description": "Visual step",
            }
        ],
        "artifacts": {},
    }
    cmd = asyncio.run(patch_planner_node(state, {}))
    assert cmd.goto == "patch_gate"
    op = cmd.update["plan_patch_log"][0]
    assert op["op"] == "append_tail"
    steps = op["payload"]["steps"]
    assert steps[0]["capability"] == "visualizer"
    assert steps[0]["title"] == "再生成"
    assert steps[0]["target_scope"]["slide_numbers"] == [2]
    assert steps[1]["capability"] == "data_analyst"


def test_patch_planner_uses_asset_unit_ledger_when_scope_not_explicit() -> None:
    state = {
        "messages": [HumanMessage(content="この画像の色味だけ修正して")],
        "request_intent": "refine",
        "product_type": "slide_infographic",
        "plan": [
            {
                "id": 1,
                "status": "pending",
                "capability": "visualizer",
                "instruction": "既存画像を生成",
                "title": "Visual",
                "description": "Visual step",
            }
        ],
        "asset_unit_ledger": {
            "slide:2": {
                "unit_id": "slide:2",
                "unit_kind": "slide",
                "unit_index": 2,
                "artifact_id": "step_9_visual",
                "image_url": "https://example.com/slide-2.png",
            }
        },
        "artifacts": {},
    }
    cmd = asyncio.run(patch_planner_node(state, {}))
    assert cmd.goto == "patch_gate"
    op = cmd.update["plan_patch_log"][0]
    assert op["op"] == "edit_pending"
    assert op["payload"]["target_scope"]["asset_unit_ids"] == ["slide:2"]
    assert op["payload"]["target_scope"]["asset_units"][0]["image_url"] == "https://example.com/slide-2.png"


def test_patch_gate_completed_step_edit_is_downgraded_to_append_with_warning() -> None:
    state = {
        "messages": [],
        "plan": [
            {"id": 1, "status": "completed", "capability": "writer", "instruction": "old", "description": "d1"},
        ],
        "artifacts": {},
        "plan_patch_log": [{"op": "edit_pending", "target_step_id": 1, "payload": {"instruction": "new"}}],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert len(cmd.update["plan"]) == 2
    assert cmd.update["plan"][0]["status"] == "completed"
    assert cmd.update["plan"][1]["status"] == "pending"
    assert cmd.update["messages"][0].additional_kwargs["result_code"] == "patch_applied_with_warnings"


def test_patch_gate_invalid_edit_payload_key_is_ignored_with_warning() -> None:
    state = {
        "messages": [],
        "plan": [{"id": 1, "status": "pending", "capability": "writer", "instruction": "old"}],
        "artifacts": {},
        "plan_patch_log": [
            {"op": "edit_pending", "target_step_id": 1, "payload": {"unknown_field": "x"}}
        ],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["instruction"] == "old"
    assert cmd.update["messages"][0].additional_kwargs["result_code"] == "patch_applied_with_warnings"


def test_patch_gate_allows_missing_dependency_reference_without_hard_error() -> None:
    state = {
        "messages": [],
        "plan": [{"id": 1, "status": "pending", "capability": "writer", "instruction": "old"}],
        "artifacts": {},
        "plan_patch_log": [
            {"op": "edit_pending", "target_step_id": 1, "payload": {"depends_on": [999]}}
        ],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["depends_on"] == [999]


def test_patch_gate_allows_dependency_cycle_without_hard_error() -> None:
    state = {
        "messages": [],
        "plan": [
            {"id": 1, "status": "pending", "capability": "writer", "instruction": "s1", "depends_on": []},
            {"id": 2, "status": "pending", "capability": "visualizer", "instruction": "s2", "depends_on": [1]},
        ],
        "artifacts": {},
        "plan_patch_log": [
            {"op": "edit_pending", "target_step_id": 1, "payload": {"depends_on": [2]}}
        ],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["depends_on"] == [2]


def test_patch_gate_duplicate_pending_step_on_append_is_allowed() -> None:
    duplicate_step = {
        "capability": "visualizer",
        "mode": "slide_render",
        "instruction": "同じ処理",
        "title": "同じ処理",
        "description": "同じ処理",
        "inputs": ["existing_artifacts"],
        "outputs": ["patched_visual"],
        "preconditions": [],
        "validation": ["ok"],
        "success_criteria": ["ok"],
        "fallback": [],
        "depends_on": [],
        "target_scope": {"asset_unit_ids": ["slide:2"]},
    }
    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "status": "pending",
                **duplicate_step,
            }
        ],
        "artifacts": {},
        "plan_patch_log": [{"op": "append_tail", "payload": {"steps": [duplicate_step]}}],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert len(cmd.update["plan"]) == 2


def test_patch_gate_invalid_target_scope_asset_unit_is_downgraded_to_warning() -> None:
    state = {
        "messages": [],
        "plan": [{"id": 1, "status": "pending", "capability": "writer", "instruction": "old"}],
        "artifacts": {},
        "asset_unit_ledger": {"slide:2": {"unit_id": "slide:2", "unit_kind": "slide", "unit_index": 2}},
        "plan_patch_log": [
            {
                "op": "edit_pending",
                "target_step_id": 1,
                "payload": {"target_scope": {"asset_unit_ids": ["invalid-unit"]}},
            }
        ],
    }
    cmd = asyncio.run(patch_gate_node(state, {}))
    assert cmd.goto == "supervisor"
    assert "target_scope" not in cmd.update["plan"][0]
    assert cmd.update["messages"][0].additional_kwargs["result_code"] == "patch_applied_with_warnings"


def test_retry_or_alt_mode_retries_same_mode_first() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 3,
                "status": "blocked",
                "capability": "visualizer",
                "instruction": "render",
                "description": "rendering",
                "result_summary": "Error: failed",
            }
        ],
        "artifacts": {},
        "rethink_used_turn": 0,
        "rethink_used_by_step": {},
    }
    cmd = asyncio.run(retry_or_alt_mode_node(state, {}))
    assert cmd.goto == "visualizer"
    assert cmd.update["rethink_used_turn"] == 1
    assert cmd.update["rethink_used_by_step"][3] == 1
    assert cmd.update["plan"][0]["status"] == "in_progress"


def test_retry_or_alt_mode_appends_fallback_on_second_retry() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 5,
                "status": "blocked",
                "capability": "writer",
                "instruction": "compose",
                "description": "compose story",
                "result_summary": "Error: fail",
            }
        ],
        "artifacts": {},
        "rethink_used_turn": 1,
        "rethink_used_by_step": {5: 1},
    }
    cmd = asyncio.run(retry_or_alt_mode_node(state, {}))
    assert cmd.goto == "supervisor"
    assert len(cmd.update["plan"]) == 2
    assert cmd.update["plan"][1]["status"] == "pending"
    assert "代替アプローチ" in cmd.update["plan"][1]["instruction"]
    assert cmd.update["rethink_used_by_step"][5] == 2
    assert cmd.update["rethink_used_turn"] == 2


def test_retry_or_alt_mode_stops_after_limit() -> None:
    state = {
        "messages": [],
        "plan": [{"id": 5, "status": "blocked", "capability": "writer"}],
        "artifacts": {},
        "rethink_used_turn": 6,
        "rethink_used_by_step": {5: 2},
    }
    cmd = asyncio.run(retry_or_alt_mode_node(state, {}))
    assert cmd.goto == "__end__"
    assert cmd.update == {}


def test_retry_or_alt_mode_resolves_capability_only_step() -> None:
    state = {
        "messages": [],
        "plan": [{"id": 6, "status": "blocked", "capability": "writer", "instruction": "rewrite"}],
        "artifacts": {},
        "rethink_used_turn": 0,
        "rethink_used_by_step": {},
    }
    cmd = asyncio.run(retry_or_alt_mode_node(state, {}))
    assert cmd.goto == "writer"
    assert cmd.update["plan"][0]["status"] == "in_progress"


def test_retry_or_alt_mode_stops_when_missing_research_detected() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 7,
                "status": "blocked",
                "capability": "visualizer",
                "instruction": "画像生成",
                "description": "ビジュアル作成",
                "title": "Visual",
                "result_summary": "Error: failed",
            }
        ],
        "artifacts": {},
        "rethink_used_turn": 0,
        "rethink_used_by_step": {},
        "quality_reports": {
            7: {
                "step_id": 7,
                "passed": False,
                "failed_checks": ["missing_research"],
                "notes": "research evidence missing",
            }
        },
    }
    cmd = asyncio.run(retry_or_alt_mode_node(state, {}))
    assert cmd.goto == "__end__"
    assert cmd.update == {}


def test_supervisor_captures_explicit_failed_checks_from_artifact() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 2,
                "capability": "writer",
                "status": "in_progress",
                "title": "Story",
                "description": "Write story",
                "instruction": "Write story",
                "result_summary": "Error: failed",
            }
        ],
        "artifacts": {
            "step_2_story": json.dumps(
                {
                    "error": "missing source references",
                    "failed_checks": ["worker_execution", "missing_research"],
                    "notes": "sources required",
                }
            )
        },
        "quality_reports": {},
    }
    cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "retry_or_alt_mode"
    assert cmd.update["quality_reports"][2]["failed_checks"] == ["missing_research", "worker_execution"]


def test_supervisor_routes_failed_artifact_to_retry_node() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "status": "in_progress",
                "title": "Story",
                "description": "Write story",
                "instruction": "Write story",
                "result_summary": "Error: generation failed",
            }
        ],
        "artifacts": {"step_1_story": json.dumps({"error": "failed"})},
        "quality_reports": {},
    }
    cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "retry_or_alt_mode"
    assert cmd.update["plan"][0]["status"] == "blocked"


def test_supervisor_emits_plan_step_started_event_for_pending_step() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "status": "pending",
                "title": "Story",
                "description": "Write story",
                "instruction": "Write story",
            }
        ],
        "artifacts": {},
    }

    with patch("src.core.workflow.nodes.supervisor.adispatch_custom_event", new=AsyncMock()) as dispatch_mock, patch(
        "src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")
    ):
        cmd = asyncio.run(supervisor_node(state, {}))

    assert cmd.goto == "writer"
    event_names = [call.args[0] for call in dispatch_mock.await_args_list]
    assert "data-plan_step_started" in event_names
    assert "plan_update" in event_names

    start_call = next(call for call in dispatch_mock.await_args_list if call.args[0] == "data-plan_step_started")
    assert start_call.args[1]["step_id"] == 1
    assert start_call.args[1]["status"] == "in_progress"


def test_supervisor_emits_plan_step_ended_event_for_completed_step() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "status": "in_progress",
                "title": "Story",
                "description": "Write story",
                "instruction": "Write story",
            }
        ],
        "artifacts": {"step_1_story": json.dumps({"execution_summary": "ok"})},
    }

    with patch("src.core.workflow.nodes.supervisor.adispatch_custom_event", new=AsyncMock()) as dispatch_mock, patch(
        "src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")
    ):
        cmd = asyncio.run(supervisor_node(state, {}))

    assert cmd.goto == "supervisor"
    event_names = [call.args[0] for call in dispatch_mock.await_args_list]
    assert "data-plan_step_ended" in event_names
    assert "plan_update" in event_names

    end_call = next(call for call in dispatch_mock.await_args_list if call.args[0] == "data-plan_step_ended")
    assert end_call.args[1]["step_id"] == 1
    assert end_call.args[1]["status"] == "completed"
