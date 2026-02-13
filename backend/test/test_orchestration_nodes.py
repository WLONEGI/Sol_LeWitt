import asyncio
import json
from unittest.mock import AsyncMock, patch

from src.core.workflow.nodes.supervisor import supervisor_node


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
    with patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")):
        cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["status"] == "completed"


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
    with patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")):
        cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["status"] == "completed"


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
    assert cmd.goto == "data_analyst"


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
                    "execution_log": "処理は完了しました。",
                    "failed_checks": ["tool_execution"],
                }
            )
        },
        "quality_reports": {},
    }
    with patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")):
        cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["status"] == "completed"


def test_supervisor_routes_visualizer_all_images_failed_to_retry_node() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 13,
                "capability": "visualizer",
                "status": "in_progress",
                "title": "Visual",
                "description": "Render visual assets",
                "instruction": "Render visuals",
                "result_summary": "処理は完了しました。",
            }
        ],
        "artifacts": {
            "step_13_visual": json.dumps(
                {
                    "execution_summary": "画像生成を完了しました。",
                    "prompts": [
                        {"slide_number": 1, "generated_image_url": None},
                        {"slide_number": 2, "generated_image_url": ""},
                    ],
                }
            )
        },
        "quality_reports": {},
    }
    with patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")):
        cmd = asyncio.run(supervisor_node(state, {}))
    assert cmd.goto == "supervisor"
    assert cmd.update["plan"][0]["status"] == "completed"


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


def test_supervisor_selects_assets_from_research_upload_and_data_outputs() -> None:
    research_gcs_url = "gs://demo-bucket/research/ref_01.png"
    upload_url = "https://storage.googleapis.com/demo-bucket/user_uploads/u1.png"
    data_image_url = "https://storage.googleapis.com/demo-bucket/generated/analysis_chart.png"
    data_pdf_url = "https://storage.googleapis.com/demo-bucket/generated/report.pdf"

    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "capability": "researcher",
                "mode": "text_search",
                "status": "completed",
                "title": "Research",
            },
            {
                "id": 2,
                "capability": "data_analyst",
                "mode": "python_pipeline",
                "status": "completed",
                "title": "Data",
            },
            {
                "id": 3,
                "capability": "visualizer",
                "mode": "slide_render",
                "status": "pending",
                "title": "Visual",
                "description": "render visuals",
                "instruction": "調査画像と分析結果を使って生成",
                "inputs": ["research:reference_images", "analysis_assets"],
                "depends_on": [1, 2],
            },
        ],
        "artifacts": {
            "step_1_research_1": json.dumps(
                {
                    "task_id": 1,
                    "perspective": "参照画像",
                    "report": "ok",
                    "search_mode": "text_search",
                    "stored_images": [
                        {
                            "gcs_url": research_gcs_url,
                            "source_url": "https://example.com/ref",
                            "caption": "research ref",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "step_2_data": json.dumps(
                {
                    "implementation_code": "print('done')",
                    "execution_log": "done",
                    "output_value": None,
                    "output_files": [
                        {"url": data_image_url, "mime_type": "image/png"},
                        {"url": data_pdf_url, "mime_type": "application/pdf"},
                    ],
                },
                ensure_ascii=False,
            ),
        },
        "attachments": [
            {
                "id": "a1",
                "filename": "upload.png",
                "mime_type": "image/png",
                "url": upload_url,
                "kind": "image",
            }
        ],
        "selected_image_inputs": [],
        "asset_pool": {},
        "selected_assets_by_step": {},
    }

    async def _mock_structured_output(*args, **kwargs):
        from src.core.workflow.nodes.supervisor import StepAssetSelection

        messages = kwargs.get("messages") or []
        selector_payload = json.loads(messages[-1].content)
        candidate_assets = selector_payload.get("candidate_assets", [])
        selected_ids = [
            str(asset.get("asset_id"))
            for asset in candidate_assets
            if str(asset.get("uri")) in {research_gcs_url, upload_url, data_image_url, data_pdf_url}
        ]
        return StepAssetSelection(selected_asset_ids=selected_ids, reason="test")

    with patch("src.core.workflow.nodes.supervisor.get_llm_by_type", return_value=object()), patch(
        "src.core.workflow.nodes.supervisor.run_structured_output", new=AsyncMock(side_effect=_mock_structured_output)
    ), patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")), patch(
        "src.core.workflow.nodes.supervisor.adispatch_custom_event", new=AsyncMock()
    ):
        cmd = asyncio.run(supervisor_node(state, {}))

    assert cmd.goto == "visualizer"
    assert cmd.update["plan"][2]["status"] == "in_progress"

    selected_map = cmd.update.get("selected_assets_by_step") or {}
    selected_ids = selected_map.get("3")
    assert isinstance(selected_ids, list)

    catalog = cmd.update.get("asset_catalog") or {}
    assert isinstance(catalog, dict)
    uris = {str(item.get("uri")) for item in catalog.values() if isinstance(item, dict)}
    assert research_gcs_url in uris
    assert upload_url in uris
    assert data_image_url in uris
    assert data_pdf_url in uris

    selected_uris = {
        str((catalog.get(asset_id) or {}).get("uri"))
        for asset_id in selected_ids
        if isinstance(asset_id, str)
    }
    assert research_gcs_url in selected_uris
    assert upload_url in selected_uris
    assert data_image_url in selected_uris


def test_supervisor_resolves_asset_requirements_and_persists_bindings() -> None:
    upload_url = "https://storage.googleapis.com/demo-bucket/user_uploads/style_ref.png"
    layout_url = "https://storage.googleapis.com/demo-bucket/generated/layout_ref.png"

    state = {
        "messages": [],
        "plan": [
            {
                "id": 1,
                "capability": "writer",
                "mode": "slide_outline",
                "status": "completed",
                "title": "Story",
            },
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "slide_render",
                "status": "pending",
                "title": "Visual",
                "description": "render visuals",
                "instruction": "テンプレート準拠で生成",
                "inputs": ["story", "style_reference"],
                "depends_on": [1],
                "asset_requirements": [
                    {
                        "role": "style_reference",
                        "required": True,
                        "scope": "global",
                        "mime_allow": ["image/*"],
                        "source_preference": ["user_upload"],
                        "max_items": 1,
                    },
                    {
                        "role": "layout_reference",
                        "required": True,
                        "scope": "global",
                        "mime_allow": ["image/*"],
                        "source_preference": ["dependency_artifact"],
                        "max_items": 1,
                    },
                ],
            },
        ],
        "artifacts": {
            "step_1_story": json.dumps(
                {
                    "execution_summary": "ok",
                    "layout_reference": {"url": layout_url, "mime_type": "image/png"},
                },
                ensure_ascii=False,
            )
        },
        "attachments": [
            {
                "id": "a1",
                "filename": "style.png",
                "mime_type": "image/png",
                "url": upload_url,
                "kind": "image",
            }
        ],
        "selected_image_inputs": [],
        "asset_pool": {},
        "selected_assets_by_step": {},
        "asset_bindings_by_step": {},
    }

    async def _mock_structured_output(*args, **kwargs):
        from src.core.workflow.nodes.supervisor import (
            RequirementAssetBinding,
            StepAssetBindingSelection,
        )

        messages = kwargs.get("messages") or []
        selector_payload = json.loads(messages[-1].content)
        if "asset_requirements" not in selector_payload:
            return StepAssetBindingSelection(bindings=[])

        candidate_assets_by_role = selector_payload.get("candidate_assets_by_role", {})
        bindings = []
        for role in ("style_reference", "layout_reference"):
            candidates = candidate_assets_by_role.get(role, [])
            if not candidates:
                bindings.append(RequirementAssetBinding(role=role, asset_ids=[], reason="no_candidate"))
                continue
            candidate_id = str(candidates[0].get("asset_id"))
            bindings.append(RequirementAssetBinding(role=role, asset_ids=[candidate_id], reason="test"))
        return StepAssetBindingSelection(bindings=bindings)

    with patch("src.core.workflow.nodes.supervisor.get_llm_by_type", return_value=object()), patch(
        "src.core.workflow.nodes.supervisor.run_structured_output", new=AsyncMock(side_effect=_mock_structured_output)
    ), patch("src.core.workflow.nodes.supervisor._generate_supervisor_report", new=AsyncMock(return_value="ok")), patch(
        "src.core.workflow.nodes.supervisor.adispatch_custom_event", new=AsyncMock()
    ):
        cmd = asyncio.run(supervisor_node(state, {}))

    assert cmd.goto == "visualizer"
    selected_map = cmd.update.get("selected_assets_by_step") or {}
    binding_map = cmd.update.get("asset_bindings_by_step") or {}
    selected_ids = selected_map.get("2") or []
    bindings = binding_map.get("2") or []
    assert len(selected_ids) == 2
    assert isinstance(bindings, list) and len(bindings) == 2

    role_to_binding = {str(item.get("role")): item for item in bindings if isinstance(item, dict)}
    assert "style_reference" in role_to_binding
    assert "layout_reference" in role_to_binding

    pool = cmd.update.get("asset_catalog") or {}
    selected_uris = {
        str((pool.get(asset_id) or {}).get("uri"))
        for asset_id in selected_ids
        if isinstance(asset_id, str)
    }
    assert upload_url in selected_uris
    assert layout_url in selected_uris
