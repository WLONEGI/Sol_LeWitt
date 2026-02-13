import asyncio
import json

from langgraph.types import Send

from src.core.workflow.nodes.researcher import research_manager_node


def test_research_manager_dispatches_next_task_by_index_even_when_task_ids_duplicate() -> None:
    state = {
        "plan": [
            {
                "id": 10,
                "capability": "researcher",
                "status": "in_progress",
                "instruction": "調査する",
            }
        ],
        "internal_research_tasks": [
            {
                "id": 1,
                "perspective": "観点A",
                "query_hints": ["A"],
                "priority": "high",
                "expected_output": "A",
                "search_mode": "text_search",
            },
            {
                "id": 1,
                "perspective": "観点B",
                "query_hints": ["B"],
                "priority": "medium",
                "expected_output": "B",
                "search_mode": "text_search",
            },
        ],
        "internal_research_results": [
            {
                "task_id": 1,
                "perspective": "観点A",
                "report": "ok",
                "sources": [],
                "image_candidates": [],
                "confidence": 0.9,
            }
        ],
        "is_decomposed": True,
        "current_task_index": 1,
        "messages": [],
        "artifacts": {},
    }

    cmd = asyncio.run(research_manager_node(state, {}))

    assert isinstance(cmd.goto, Send)
    assert cmd.goto.node == "research_worker"
    assert cmd.update == {"current_task_index": 2}
    assert cmd.goto.arg["task"]["perspective"] == "観点B"


def test_research_manager_emits_failure_artifact_when_state_is_inconsistent() -> None:
    state = {
        "plan": [
            {
                "id": 11,
                "capability": "researcher",
                "status": "in_progress",
                "instruction": "調査する",
                "result_summary": None,
            }
        ],
        "internal_research_tasks": [
            {
                "id": 1,
                "perspective": "観点A",
                "query_hints": ["A"],
                "priority": "high",
                "expected_output": "A",
                "search_mode": "text_search",
            },
            {
                "id": 2,
                "perspective": "観点B",
                "query_hints": ["B"],
                "priority": "medium",
                "expected_output": "B",
                "search_mode": "text_search",
            },
        ],
        "internal_research_results": [
            {
                "task_id": 1,
                "perspective": "観点A",
                "report": "ok",
                "sources": [],
                "image_candidates": [],
                "confidence": 0.9,
            }
        ],
        "is_decomposed": True,
        "current_task_index": 2,
        "messages": [],
        "artifacts": {},
    }

    cmd = asyncio.run(research_manager_node(state, {}))

    assert cmd.goto == "__end__"
    assert isinstance(cmd.update, dict)
    assert cmd.update["is_decomposed"] is False
    assert cmd.update["current_task_index"] == 0

    artifact_raw = cmd.update["artifacts"]["step_11_research"]
    artifact_payload = json.loads(artifact_raw)
    assert artifact_payload["failed_checks"] == ["research_manager_state_inconsistent"]
    assert "inconsistent sequential state" in artifact_payload["summary"]
    assert "inconsistent sequential state" in cmd.update["plan"][0]["result_summary"]
