from src.core.workflow.nodes.planner import (
    _build_attachment_signal,
    _ensure_multi_perspective_research_steps,
    _missing_required_research_step,
)


def test_missing_required_research_step_when_user_request_demands_sources() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "スライド構成を作成する",
        },
        {
            "id": 2,
            "capability": "visualizer",
            "instruction": "画像生成を行う",
        },
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "中世情報の出典を調査してから漫画を作って",
    )
    assert missing is True
    assert "Research requirement" in reason


def test_missing_required_research_step_when_step_requires_reference() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "出典を併記した構成案を作る",
        }
    ]
    missing, _ = _missing_required_research_step(
        plan_steps,
        "資料をもとにスライド化して",
    )
    assert missing is True


def test_no_missing_when_research_step_is_explicit() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "researcher",
            "instruction": "中世資料を調査する",
        },
        {
            "id": 2,
            "capability": "writer",
            "instruction": "調査結果をもとに脚本を作成する",
        },
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "中世の出典を必ず含めて漫画化して",
    )
    assert missing is False
    assert reason == ""


def test_no_missing_when_research_not_required() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "writer",
            "instruction": "既存設定から漫画プロットを作る",
        }
    ]
    missing, reason = _missing_required_research_step(
        plan_steps,
        "このプロットを4ページ漫画にして",
    )
    assert missing is False
    assert reason == ""


def test_research_step_instruction_is_enriched_with_multiple_perspectives() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "researcher",
            "instruction": "SaaSのQBRについて調査する",
            "description": "調査タスク",
        }
    ]

    enriched = _ensure_multi_perspective_research_steps(plan_steps, product_type="slide")
    instruction = enriched[0]["instruction"]
    assert "調査観点" in instruction
    assert instruction.count("- ") >= 3


def test_research_step_instruction_is_not_overwritten_when_already_multi_perspective() -> None:
    plan_steps = [
        {
            "id": 1,
            "capability": "researcher",
            "instruction": "調査観点:\n- 市場動向\n- 先行事例\n- リスク",
            "description": "調査タスク",
        }
    ]

    enriched = _ensure_multi_perspective_research_steps(plan_steps, product_type="slide")
    assert enriched[0]["instruction"] == plan_steps[0]["instruction"]


def test_build_attachment_signal_detects_pptx_from_attachments() -> None:
    signal = _build_attachment_signal(
        {
            "attachments": [
                {
                    "filename": "template.pptx",
                    "kind": "pptx",
                    "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                }
            ]
        }
    )
    assert signal["has_pptx_attachment"] is True
    assert signal["pptx_attachment_count"] == 1
    assert signal["pptx_context_template_count"] == 0


def test_build_attachment_signal_detects_pptx_from_context_only() -> None:
    signal = _build_attachment_signal(
        {
            "attachments": [],
            "pptx_context": {
                "template_count": 1,
                "templates": [{"filename": "template.pptx"}],
            },
        }
    )
    assert signal["has_pptx_attachment"] is True
    assert signal["pptx_attachment_count"] == 0
    assert signal["pptx_context_template_count"] == 1
