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


def test_visualizer_design_previous_reference_policy_uses_previous_generated_image() -> None:
    state = {
        "messages": [],
        "product_type": "design",
        "plan": [
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "document_layout_render",
                "status": "in_progress",
                "title": "Design Render",
                "description": "Render design pages",
                "instruction": "Render document layout pages",
            }
        ],
        "artifacts": {
            "step_1_story": json.dumps(
                {
                    "execution_summary": "outline created",
                    "user_message": "ok",
                    "slides": [
                        {
                            "slide_number": 1,
                            "title": "Page 1",
                            "description": "Intro",
                            "bullet_points": ["A", "B"],
                        },
                        {
                            "slide_number": 2,
                            "title": "Page 2",
                            "description": "Detail",
                            "bullet_points": ["C", "D"],
                        },
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
        generation_order=[1, 2],
        slides=[
            VisualizerPlanSlide(
                slide_number=1,
                layout_type="title_and_content",
                selected_inputs=[],
                reference_policy="none",
                reference_url=None,
                generation_notes=None,
            ),
            VisualizerPlanSlide(
                slide_number=2,
                layout_type="title_and_content",
                selected_inputs=[],
                reference_policy="previous",
                reference_url=None,
                generation_notes=None,
            ),
        ],
    )

    prompt1 = ImagePrompt(
        slide_number=1,
        image_generation_prompt="prompt-1",
        rationale="r1",
    )
    prompt2 = ImagePrompt(
        slide_number=2,
        image_generation_prompt="prompt-2",
        rationale="r2",
    )

    async def _mock_process_single_slide(prompt_item, **kwargs):
        if prompt_item.slide_number == 1:
            prompt_item.generated_image_url = "https://example.com/generated-1.png"
            return prompt_item, b"img-1", None
        if prompt_item.slide_number == 2:
            assert kwargs.get("override_reference_url") == "https://example.com/generated-1.png"
            assert kwargs.get("override_reference_bytes") == b"prev-image-bytes"
            prompt_item.generated_image_url = "https://example.com/generated-2.png"
            return prompt_item, b"img-2", None
        raise AssertionError("unexpected slide number")

    with patch("src.core.workflow.nodes.visualizer.get_llm_by_type", return_value=object()), patch(
        "src.core.workflow.nodes.visualizer.apply_prompt_template",
        return_value=[HumanMessage(content="visualizer prompt")],
    ), patch(
        "src.core.workflow.nodes.visualizer.run_structured_output",
        new=AsyncMock(side_effect=[plan, prompt1, prompt2]),
    ), patch(
        "src.core.workflow.nodes.visualizer._plan_visual_asset_usage",
        new=AsyncMock(return_value={}),
    ), patch(
        "src.core.workflow.nodes.visualizer.process_single_slide",
        new=AsyncMock(side_effect=_mock_process_single_slide),
    ), patch(
        "src.core.workflow.nodes.visualizer.download_blob_as_bytes",
        return_value=b"prev-image-bytes",
    ) as mock_download, patch(
        "src.core.workflow.nodes.visualizer.adispatch_custom_event",
        new=AsyncMock(),
    ), patch(
        "src.core.workflow.nodes.visualizer._get_thread_title",
        new=AsyncMock(return_value="Design Demo"),
    ):
        cmd = asyncio.run(
            visualizer_node(
                state,
                {"configurable": {"thread_id": "thread-design-1", "user_uid": "user-1"}},
            )
        )

    assert cmd.goto == "supervisor"
    assert mock_download.call_count >= 1
    assert "step_2_visual" in cmd.update["artifacts"]
    payload = json.loads(cmd.update["artifacts"]["step_2_visual"])
    assert payload["product_type"] == "design"
    assert isinstance(payload.get("design_pages"), list)
    assert len(payload["design_pages"]) == 2


def test_visualizer_comic_uses_previous_generated_page_as_reference() -> None:
    state = {
        "messages": [],
        "product_type": "comic",
        "plan": [
            {
                "id": 5,
                "capability": "visualizer",
                "mode": "comic_page_render",
                "status": "in_progress",
                "title": "Comic Page Render",
                "description": "Render comic pages",
                "instruction": "Render comic pages",
            }
        ],
        "artifacts": {
            "step_1_story": json.dumps(
                {
                    "execution_summary": "character sheet created",
                    "user_message": "ok",
                    "characters": [
                        {
                            "character_id": "hero_01",
                            "name": "ヒーロー",
                            "story_role": "主人公",
                            "core_personality": "冷静",
                            "motivation": "街を守る",
                            "weakness_or_fear": "仲間の負傷",
                            "silhouette_signature": "長いマント",
                            "face_hair_anchors": "短髪",
                            "costume_anchors": "黒いスーツ",
                            "color_palette": {"main": "#111111", "sub": "#666666", "accent": "#E6E6E6"},
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
                    "user_message": "ok",
                    "pages": [
                        {
                            "page_number": 1,
                            "page_goal": "導入",
                            "panels": [{"panel_number": 1, "foreground": "ヒーローが立つ"}],
                        },
                        {
                            "page_number": 2,
                            "page_goal": "展開",
                            "panels": [{"panel_number": 1, "foreground": "ヒーローが走る"}],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            "step_3_visual": json.dumps(
                {
                    "product_type": "comic",
                    "mode": "character_sheet_render",
                    "characters": [
                        {
                            "character_number": 1,
                            "generated_image_url": "https://example.com/character-1.png",
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

    plan = VisualizerPlan(
        execution_summary="visual plan ready",
        generation_order=[1, 2],
        slides=[
            VisualizerPlanSlide(
                slide_number=1,
                layout_type="other",
                selected_inputs=[],
                reference_policy="none",
                reference_url=None,
                generation_notes=None,
            ),
            VisualizerPlanSlide(
                slide_number=2,
                layout_type="other",
                selected_inputs=[],
                reference_policy="none",
                reference_url=None,
                generation_notes=None,
            ),
        ],
    )

    async def _mock_process_single_slide(prompt_item, **kwargs):
        if prompt_item.slide_number == 1:
            assert kwargs.get("override_reference_url") in (None, "")
            prompt_item.generated_image_url = "https://example.com/comic-1.png"
            return prompt_item, b"img-1", None
        if prompt_item.slide_number == 2:
            assert kwargs.get("override_reference_url") == "https://example.com/comic-1.png"
            assert kwargs.get("override_reference_bytes") == b"prev-page-bytes"
            prompt_item.generated_image_url = "https://example.com/comic-2.png"
            return prompt_item, b"img-2", None
        raise AssertionError("unexpected slide number")

    with patch("src.core.workflow.nodes.visualizer.get_llm_by_type", return_value=object()), patch(
        "src.core.workflow.nodes.visualizer.apply_prompt_template",
        return_value=[HumanMessage(content="visualizer prompt")],
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
        "src.core.workflow.nodes.visualizer.download_blob_as_bytes",
        return_value=b"prev-page-bytes",
    ) as mock_download, patch(
        "src.core.workflow.nodes.visualizer.adispatch_custom_event",
        new=AsyncMock(),
    ), patch(
        "src.core.workflow.nodes.visualizer._get_thread_title",
        new=AsyncMock(return_value="Comic Demo"),
    ):
        cmd = asyncio.run(
            visualizer_node(
                state,
                {"configurable": {"thread_id": "thread-comic-1", "user_uid": "user-1"}},
            )
        )

    assert cmd.goto == "supervisor"
    assert mock_download.call_count >= 1
    assert "step_5_visual" in cmd.update["artifacts"]
    payload = json.loads(cmd.update["artifacts"]["step_5_visual"])
    assert payload["product_type"] == "comic"
    assert isinstance(payload.get("comic_pages"), list)
    assert len(payload["comic_pages"]) == 2
