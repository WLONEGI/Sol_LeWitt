import json

from langchain_core.messages import AIMessage, HumanMessage

from src.app.app import _build_snapshot_payload, _serialize_message


def test_serialize_message_keeps_reasoning_and_plan_data_parts() -> None:
    message = AIMessage(
        content="Plan Created",
        additional_kwargs={
            "reasoning_content": "think step by step",
            "ui_type": "plan_update",
            "plan": [{"id": 1, "title": "Research", "status": "in_progress"}],
            "title": "Execution Plan",
            "description": "Updated",
        },
    )

    serialized = _serialize_message(message)
    assert serialized is not None
    assert serialized["role"] == "assistant"
    assert serialized["content"] == "Plan Created"

    parts = serialized["parts"]
    assert parts[0] == {"type": "reasoning", "text": "think step by step"}
    assert any(part.get("type") == "data-plan_update" for part in parts)


def test_build_snapshot_payload_generates_ui_events_and_artifacts() -> None:
    state_values = {
        "messages": [
            HumanMessage(content="こんにちは"),
            AIMessage(content="作成を開始します"),
        ],
        "plan": [{"id": 1, "title": "Story", "status": "complete"}],
        "artifacts": {
            "step_1_story": json.dumps(
                {
                    "slides": [
                        {
                            "slide_number": 1,
                            "title": "Intro",
                            "bullet_points": ["A", "B"],
                            "description": "summary",
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            "step_2_visual": json.dumps(
                {
                    "prompts": [
                        {
                            "slide_number": 1,
                            "title": "Intro Visual",
                            "generated_image_url": "https://example.com/s1.png",
                            "compiled_prompt": "prompt text",
                            "structured_prompt": {"main_title": "Intro"},
                            "rationale": "fit to message",
                            "layout_type": "title_slide",
                        }
                    ],
                    "combined_pdf_url": "https://example.com/deck.pdf",
                },
                ensure_ascii=False,
            ),
            "step_3_data": json.dumps(
                {
                    "execution_summary": "completed",
                    "analysis_report": "report",
                    "output_files": [],
                },
                ensure_ascii=False,
            ),
        },
    }

    snapshot = _build_snapshot_payload("thread-1", state_values)

    assert snapshot["thread_id"] == "thread-1"
    assert len(snapshot["messages"]) == 2

    artifacts = snapshot["artifacts"]
    assert artifacts["step_1_story"]["type"] == "outline"
    assert artifacts["step_2_visual"]["type"] == "slide_deck"
    assert artifacts["step_3_data"]["type"] == "data_analyst"

    event_types = [event["type"] for event in snapshot["ui_events"]]
    assert "data-plan_update" in event_types
    assert "data-outline" in event_types
    assert "data-visual-image" in event_types
    assert "data-visual-pdf" in event_types
    assert "data-analyst-output" in event_types
    assert "data-writer-output" in event_types


def test_build_snapshot_payload_supports_writer_structured_artifacts() -> None:
    state_values = {
        "messages": [],
        "plan": [],
        "artifacts": {
            "step_10_story": json.dumps(
                {
                    "execution_summary": "framework completed",
                    "user_message": "Story framework ready.",
                    "story_framework": {
                        "concept": "A young inventor rewrites a kingdom's fate.",
                        "theme": "Hope under pressure",
                        "format_policy": {
                            "series_type": "oneshot",
                            "medium": "digital",
                            "page_budget": {"min": 24, "max": 32},
                            "reading_direction": "rtl",
                        },
                        "structure_type": "kishotenketsu",
                        "arc_overview": [
                            {"phase": "起", "purpose": "導入"},
                            {"phase": "承", "purpose": "対立拡大"},
                            {"phase": "転", "purpose": "反転"},
                            {"phase": "結", "purpose": "決着"},
                        ],
                        "core_conflict": "Inventor vs ruling guild",
                        "world_policy": {
                            "era": "Clockwork medieval city",
                            "primary_locations": ["Guild district"],
                            "social_rules": ["No unauthorized machines"],
                        },
                        "direction_policy": {
                            "paneling_policy": "5-6 panels baseline",
                            "eye_guidance_policy": "Right to left flow",
                            "page_turn_policy": "Use cliffhanger on page turns",
                            "dialogue_policy": "One idea per bubble",
                        },
                        "art_style_policy": {
                            "line_style": "G-pen main lines",
                            "shading_style": "Screentone + solid black",
                            "negative_constraints": ["photorealism", "3D render"],
                        },
                    },
                },
                ensure_ascii=False,
            )
        },
    }

    snapshot = _build_snapshot_payload("thread-2", state_values)

    artifacts = snapshot["artifacts"]
    assert artifacts["step_10_story"]["type"] == "writer_story_framework"
    assert (
        artifacts["step_10_story"]["content"]["story_framework"]["concept"]
        == "A young inventor rewrites a kingdom's fate."
    )

    writer_events = [event for event in snapshot["ui_events"] if event["type"] == "data-writer-output"]
    assert len(writer_events) == 1
    assert writer_events[0]["data"]["artifact_type"] == "writer_story_framework"
