import asyncio
import json
from unittest.mock import AsyncMock, patch

from src.core.workflow.nodes.supervisor import retry_or_alt_mode_node, supervisor_node


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
    assert cmd.update["plan"][0]["result_summary"] is None


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
    assert "[SUPERVISOR_RETRY_HINT]" in cmd.update["plan"][0]["instruction"]


def test_supervisor_routes_failed_result_summary_without_artifact_to_retry_node() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 11,
                "capability": "data_analyst",
                "status": "in_progress",
                "title": "Analyze",
                "description": "Analyze data",
                "instruction": "Analyze data and return summary",
                "result_summary": "要修正: 入力ファイルが不足しているため再実行が必要です。",
            }
        ],
        "artifacts": {},
        "quality_reports": {},
    }
    cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "retry_or_alt_mode"
    assert cmd.update["plan"][0]["status"] == "blocked"
    assert "入力ファイルが不足" in cmd.update["plan"][0]["instruction"]
    assert cmd.update["quality_reports"][11]["passed"] is False


def test_supervisor_marks_failed_checks_only_artifact_as_failed() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 12,
                "capability": "data_analyst",
                "status": "in_progress",
                "title": "Package",
                "description": "Package output",
                "instruction": "Package files",
                "result_summary": "処理は完了しました。",
            }
        ],
        "artifacts": {
            "step_12_data": json.dumps(
                {
                    "execution_summary": "処理は完了しました。",
                    "failed_checks": ["tool_execution"],
                }
            )
        },
        "quality_reports": {},
    }
    cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "retry_or_alt_mode"
    assert cmd.update["plan"][0]["status"] == "blocked"
    assert cmd.update["quality_reports"][12]["failed_checks"] == ["tool_execution"]


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
