import asyncio
import json
from unittest.mock import AsyncMock, patch

from langchain_core.messages import HumanMessage

from src.core.workflow.nodes.visualizer import process_single_slide, visualizer_node
from src.shared.schemas.outputs import VisualizerPlan, VisualizerPlanSlide
from src.shared.schemas.outputs import ImagePrompt


def test_visualizer_returns_error_when_all_images_fail() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 3,
                "capability": "visualizer",
                "mode": "character_sheet_render",
                "status": "in_progress",
                "title": "Character Render",
                "description": "Render character sheet",
                "instruction": "Render character sheet images",
            }
        ],
        "artifacts": {
            "step_2_story": json.dumps(
                {
                    "execution_summary": "character sheet created",
                    "characters": [
                        {
                            "character_id": "barista",
                            "name": "バリスタさん",
                            "story_role": "主人公",
                            "core_personality": "真面目",
                            "motivation": "完璧な一杯を提供する",
                            "weakness_or_fear": "プレッシャーに弱い",
                            "silhouette_signature": "短い前掛けと丸い帽子",
                            "face_hair_anchors": "柔らかい目元と短髪",
                            "costume_anchors": "白シャツとエプロン",
                            "color_palette": {"main": "#555555", "sub": "#AAAAAA", "accent": "#D9A441"},
                            "signature_items": [],
                            "forbidden_drift": [],
                        }
                    ],
                },
                ensure_ascii=False,
            )
        },
        "selected_image_inputs": [],
        "attachments": [],
        "asset_unit_ledger": {},
    }

    plan = VisualizerPlan(
        execution_summary="visual plan ready",
        generation_order=[1],
        slides=[
            VisualizerPlanSlide(
                slide_number=1,
                layout_type="other",
                selected_inputs=[],
                reference_policy="none",
                reference_url=None,
                generation_notes=None,
            )
        ],
    )

    async def _mock_process_single_slide(prompt_item, **_kwargs):
        prompt_item.generated_image_url = None
        return prompt_item, None, "429 RESOURCE_EXHAUSTED"

    with patch("src.core.workflow.nodes.visualizer.get_llm_by_type", return_value=object()), patch(
        "src.core.workflow.nodes.visualizer.apply_prompt_template",
        return_value=[HumanMessage(content="visualizer plan prompt")],
    ), patch(
        "src.core.workflow.nodes.visualizer.run_structured_output",
        new=AsyncMock(return_value=plan),
    ), patch(
        "src.core.workflow.nodes.visualizer._plan_visual_asset_usage",
        new=AsyncMock(return_value={}),
    ), patch(
        "src.core.workflow.nodes.visualizer.process_single_slide",
        new=AsyncMock(side_effect=_mock_process_single_slide),
    ), patch(
        "src.core.workflow.nodes.visualizer.adispatch_custom_event",
        new=AsyncMock(),
    ), patch(
        "src.core.workflow.nodes.visualizer._get_thread_title",
        new=AsyncMock(return_value="Demo"),
    ):
        cmd = asyncio.run(
            visualizer_node(
                state,
                {"configurable": {"thread_id": "thread-1", "user_uid": "user-1"}},
            )
        )

    assert cmd.goto == "supervisor"
    assert "step_3_visual" in cmd.update["artifacts"]
    payload = json.loads(cmd.update["artifacts"]["step_3_visual"])
    assert payload["error"] == "All visual image generations failed."
    assert "all_images_failed" in payload["failed_checks"]


def test_visualizer_comic_page_requires_character_sheet_rendered_images() -> None:
    state = {
        "messages": [],
        "plan": [
            {
                "id": 4,
                "capability": "visualizer",
                "mode": "comic_page_render",
                "status": "in_progress",
                "title": "Comic Page Render",
                "description": "Render comic pages",
                "instruction": "Render comic page images",
            }
        ],
        "artifacts": {
            "step_1_story": json.dumps(
                {
                    "execution_summary": "character sheet created",
                    "characters": [
                        {
                            "character_id": "hero",
                            "name": "ヒーロー",
                            "story_role": "主人公",
                            "core_personality": "冷静",
                            "motivation": "街を守る",
                            "weakness_or_fear": "仲間の負傷",
                            "silhouette_signature": "長いマント",
                            "face_hair_anchors": "短髪",
                            "costume_anchors": "黒いスーツ",
                            "color_palette": {"main": "#333333", "sub": "#777777", "accent": "#CC0000"},
                            "signature_items": [],
                            "forbidden_drift": [],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            "step_2_story": json.dumps(
                {
                    "execution_summary": "comic pages created",
                    "pages": [
                        {
                            "page_number": 1,
                            "panels": [
                                {
                                    "panel_number": 1,
                                    "foreground": "ヒーローが走る",
                                    "background": "夜の街",
                                    "composition": "斜め構図",
                                    "camera": "ロング",
                                    "lighting": "ネオン",
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
        },
        "selected_image_inputs": [],
        "attachments": [],
        "asset_unit_ledger": {},
    }

    cmd = asyncio.run(
        visualizer_node(
            state,
            {"configurable": {"thread_id": "thread-2", "user_uid": "user-1"}},
        )
    )

    assert cmd.goto == "supervisor"
    assert "step_4_visual" in cmd.update["artifacts"]
    payload = json.loads(cmd.update["artifacts"]["step_4_visual"])
    assert payload["error"] == "Character sheet rendered images are required for comic page rendering."
    assert "missing_dependency" in payload["failed_checks"]


def test_process_single_slide_uses_precompiled_prompt_without_recompile() -> None:
    prompt_item = ImagePrompt(
        slide_number=1,
        image_generation_prompt="legacy prompt should not be used",
        compiled_prompt="precompiled prompt",
        rationale="test",
    )

    with patch(
        "src.core.workflow.nodes.visualizer._resolve_image_generation_prompt",
        side_effect=AssertionError("recompile must not run when compiled_prompt exists"),
    ), patch(
        "src.core.workflow.nodes.visualizer.generate_image",
        return_value=(b"img-bytes", "api-token"),
    ) as mock_generate, patch(
        "src.core.workflow.nodes.visualizer.upload_to_gcs",
        return_value="https://example.com/generated.png",
    ):
        processed, image_bytes, error = asyncio.run(
            process_single_slide(
                prompt_item,
                mode="slide_render",
                session_id="thread-3",
            )
        )

    assert error is None
    assert image_bytes == b"img-bytes"
    assert processed.compiled_prompt == "precompiled prompt"
    assert processed.generated_image_url == "https://example.com/generated.png"
    assert mock_generate.call_args.args[0] == "precompiled prompt"
