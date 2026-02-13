import json

import pytest
from langchain_core.messages import HumanMessage

from src.app.app import _build_snapshot_payload


def _image_candidates(count: int) -> list[dict]:
    return [
        {
            "image_url": f"https://example.com/ref-{idx}.png",
            "source_url": f"https://example.com/source-{idx}",
            "license_note": "CC BY 4.0",
            "provider": "grounded_web",
            "caption": f"candidate-{idx}",
        }
        for idx in range(1, count + 1)
    ]


@pytest.mark.parametrize(
    ("product_type", "story_artifact", "expected_story_type"),
    [
        (
            "slide_infographic",
            {
                "execution_summary": "outline created",
                "slides": [
                    {
                        "slide_number": 1,
                        "title": "導入",
                        "bullet_points": ["課題", "解決案"],
                        "description": "導入スライド",
                    }
                ],
            },
            "outline",
        ),
        (
            "document_design",
            {
                "execution_summary": "blueprint created",
                "document_type": "manual",
                "style_direction": "clean and modern",
                "pages": [
                    {
                        "page_number": 1,
                        "page_title": "はじめに",
                        "purpose": "全体説明",
                        "sections": [
                            {
                                "section_id": "s1",
                                "heading": "目的",
                                "body": "本手順書の目的",
                                "visual_hint": "line icon",
                            }
                        ],
                    }
                ],
            },
            "writer_document_blueprint",
        ),
        (
            "comic",
            {
                "execution_summary": "comic script created",
                "title": "Clockwork Dawn",
                "genre": "fantasy",
                "pages": [
                    {
                        "page_number": 1,
                        "page_goal": "主人公導入",
                        "panels": [
                            {
                                "panel_number": 1,
                                "scene_description": "城下町の朝",
                                "dialogue": ["今日こそ発明を完成させる"],
                                "sfx": ["ガヤガヤ"],
                            }
                        ],
                    }
                ],
            },
            "writer_comic_script",
        ),
    ],
)
def test_category_fixed_flow_snapshot_contracts(
    product_type: str,
    story_artifact: dict,
    expected_story_type: str,
) -> None:
    selected = {
        "image_url": "https://example.com/ref-picked.png",
        "source_url": "https://example.com/source-picked",
        "license_note": "CC BY-SA 4.0",
        "provider": "grounded_web",
    }
    state_values = {
        "messages": [HumanMessage(content=f"{product_type} を新規作成")],
        "plan": [],
        "artifacts": {
            "step_1_story": json.dumps(story_artifact, ensure_ascii=False),
            "step_2_research_refs": json.dumps(
                {
                    "task_id": 1,
                    "perspective": "reference image search",
                    "report": "reference report",
                    "sources": ["https://example.com/ref-source"],
                    "image_candidates": _image_candidates(10),
                    "confidence": 0.9,
                },
                ensure_ascii=False,
            ),
            "step_3_visual": json.dumps(
                {
                    "execution_summary": "visual generated",
                    "prompts": [
                        {
                            "slide_number": 1,
                            "title": "Key Visual",
                            "generated_image_url": "https://example.com/generated-1.png",
                            "compiled_prompt": "high quality illustration",
                            "structured_prompt": {"main_title": "Key Visual"},
                            "rationale": "aligns with story",
                            "layout_type": "title_slide",
                            "selected_inputs": [selected],
                        }
                    ],
                    "generation_config": {
                        "thinking_level": "high",
                        "media_resolution": "medium",
                        "aspect_ratio": "16:9",
                    },
                },
                ensure_ascii=False,
            ),
        },
    }

    snapshot = _build_snapshot_payload(f"thread-{product_type}", state_values)

    artifacts = snapshot["artifacts"]
    assert artifacts["step_1_story"]["type"] == expected_story_type
    assert artifacts["step_3_visual"]["type"] == "slide_deck"

    ui_events = snapshot["ui_events"]
    visual_events = [event for event in ui_events if event["type"] == "data-visual-image"]
    assert len(visual_events) == 1
    selected_inputs = visual_events[0]["data"]["selected_inputs"]
    assert isinstance(selected_inputs, list) and len(selected_inputs) == 1
    assert selected_inputs[0]["image_url"] == selected["image_url"]
