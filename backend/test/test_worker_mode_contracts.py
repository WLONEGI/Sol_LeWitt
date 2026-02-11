from src.core.workflow.nodes.planner import _normalize_plan_steps
from src.shared.schemas.outputs import (
    ResearchImageCandidate,
    ResearchResult,
    ResearchTask,
    TaskStep,
    WriterStoryFrameworkOutput,
)


def test_task_step_accepts_capability_only() -> None:
    step = TaskStep(
        id=1,
        capability="writer",
        mode="comic_script",
        instruction="漫画の脚本を作成する",
    )
    dumped = step.model_dump(exclude_none=True)
    assert "role" not in dumped
    assert dumped["capability"] == "writer"
    assert dumped["instruction"] == "漫画の脚本を作成する"
    assert step.instruction == "漫画の脚本を作成する"
    assert step.title is not None
    assert step.description is not None


def test_research_task_default_search_mode() -> None:
    task = ResearchTask(
        id=1,
        perspective="Medieval references",
        query_hints=["medieval armor reference images"],
        expected_output="image references",
    )
    assert task.search_mode == "text_search"


def test_research_result_with_image_candidates() -> None:
    candidate = ResearchImageCandidate(
        image_url="https://example.com/ref.png",
        source_url="https://example.com",
        license_note="CC BY 4.0",
        provider="example",
    )
    result = ResearchResult(
        task_id=1,
        perspective="image search",
        report="report",
        sources=["https://example.com"],
        image_candidates=[candidate],
        confidence=0.8,
    )
    assert result.image_candidates[0].image_url == "https://example.com/ref.png"


def test_planner_normalize_step_uses_canonical_v2() -> None:
    steps = _normalize_plan_steps(
        [
            {
                "id": 1,
                "capability": "writer",
                "instruction": "漫画のページ構成を作る",
            }
        ],
        product_type="slide_infographic",
    )
    assert "role" not in steps[0]
    assert steps[0]["mode"] == "slide_outline"
    assert steps[0]["instruction"] == "漫画のページ構成を作る"


def test_planner_normalize_comic_keeps_model_sequence_in_hybrid_mode() -> None:
    steps = _normalize_plan_steps(
        [
            {
                "id": 1,
                "capability": "writer",
                "mode": "comic_script",
                "instruction": "先に脚本を書く",
                "depends_on": [],
            },
            {
                "id": 2,
                "capability": "visualizer",
                "mode": "comic_page_render",
                "instruction": "漫画ページを描く",
                "depends_on": [1],
            },
        ],
        product_type="comic",
    )

    assert [(step["capability"], step["mode"]) for step in steps] == [
        ("writer", "comic_script"),
        ("visualizer", "comic_page_render"),
    ]
    assert steps[1]["depends_on"] == [1]


def test_planner_normalize_comic_preserves_steps_without_auto_insertion() -> None:
    steps = _normalize_plan_steps(
        [
            {
                "id": 1,
                "capability": "researcher",
                "mode": "text_search",
                "instruction": "中世資料を調査する",
                "depends_on": [],
            },
            {
                "id": 2,
                "capability": "writer",
                "mode": "story_framework",
                "instruction": "フレームを作る",
                "depends_on": [],
            },
            {
                "id": 3,
                "capability": "writer",
                "mode": "comic_script",
                "instruction": "脚本を書く",
                "depends_on": [2],
            },
        ],
        product_type="comic",
    )

    assert steps[0]["capability"] == "researcher"
    assert steps[0]["mode"] == "text_search"
    assert [(step["capability"], step["mode"]) for step in steps] == [
        ("researcher", "text_search"),
        ("writer", "story_framework"),
        ("writer", "comic_script"),
    ]


def test_writer_story_framework_output_accepts_new_shape() -> None:
    data = {
        "execution_summary": "ok",
        "user_message": "done",
        "story_framework": {
            "concept": "新世界の再建",
            "theme": "希望と連帯",
            "format_policy": {
                "series_type": "oneshot",
                "medium": "digital",
                "page_budget": {"min": 24, "max": 32},
                "reading_direction": "rtl",
            },
            "structure_type": "kishotenketsu",
            "arc_overview": [{"phase": "起", "purpose": "導入"}],
            "core_conflict": "都市を支配する勢力との対立",
            "world_policy": {
                "era": "近未来",
                "primary_locations": ["第7区"],
                "social_rules": ["夜間外出制限"],
            },
            "direction_policy": {
                "paneling_policy": "通常5コマ",
                "eye_guidance_policy": "右上から左下",
                "page_turn_policy": "章末で反転",
                "dialogue_policy": "1フキダシ1情報",
            },
            "art_style_policy": {
                "line_style": "Gペン主線",
                "shading_style": "スクリーントーン中心",
                "negative_constraints": ["フォトリアル禁止"],
            },
        },
    }
    parsed = WriterStoryFrameworkOutput.model_validate(data)
    assert parsed.story_framework.concept == "新世界の再建"
    assert parsed.story_framework.format_policy.page_budget.min == 24


def test_writer_story_framework_output_upgrades_legacy_shape() -> None:
    legacy = {
        "execution_summary": "ok",
        "user_message": "done",
        "logline": "古い形式のログライン",
        "world_setting": "蒸気都市",
        "background_context": "旧体制との対立",
        "tone_and_temperature": "重厚",
        "narrative_arc": ["導入", "対立", "反転", "決着"],
        "constraints": ["CGI禁止"],
    }
    parsed = WriterStoryFrameworkOutput.model_validate(legacy)
    assert parsed.story_framework.concept == "古い形式のログライン"
    assert parsed.story_framework.world_policy.era == "蒸気都市"
    assert parsed.story_framework.art_style_policy.negative_constraints[0] == "CGI禁止"
