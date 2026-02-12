import json

from src.core.workflow.nodes.common import resolve_step_dependency_context
from src.core.workflow.nodes.researcher import (
    _extract_urls,
    _normalize_task_modes_by_instruction,
)
from src.shared.schemas.outputs import ResearchTask, StructuredImagePrompt
from src.core.workflow.nodes.visualizer import (
    _resolve_asset_unit_meta,
    _writer_output_to_slides,
    compile_structured_prompt,
)
from src.core.workflow.nodes.writer import _resolve_writer_mode


def test_extract_urls_deduplicates_and_trims_tail_punctuation() -> None:
    text = "ref https://example.com/a.png and https://example.com/page"
    urls = _extract_urls(text)
    assert "https://example.com/a.png" in urls
    assert "https://example.com/page" in urls
    assert len(urls) == 2


def test_writer_output_to_slides_for_comic_script() -> None:
    writer_data = {
        "pages": [
            {
                "page_number": 1,
                "page_goal": "導入",
                "panels": [
                    {"panel_number": 1, "scene_description": "城下町の朝"},
                    {"panel_number": 2, "scene_description": "主人公の登場"},
                ],
            }
        ]
    }
    slides = _writer_output_to_slides(writer_data, "comic_page_render")
    assert len(slides) == 1
    assert slides[0]["slide_number"] == 1
    assert "城下町の朝" in slides[0]["bullet_points"][0]


def test_resolve_asset_unit_meta_by_mode() -> None:
    unit_id, unit_kind, unit_index = _resolve_asset_unit_meta(
        mode="document_layout_render",
        product_type="document_design",
        slide_number=3,
    )
    assert unit_id == "page:3"
    assert unit_kind == "page"
    assert unit_index == 3


def test_compile_structured_prompt_omits_type_line() -> None:
    structured = StructuredImagePrompt(
        slide_type="Title Slide",
        main_title="SaaS主要KPIの定義と計算式",
        sub_title="経営判断に必要な共通指標",
        contents="- ARR\n- Churn",
        visual_style="clean business infographic, blue and gray palette, high contrast typography",
        text_policy="render_all_text",
        negative_constraints=["blurry text", "warped chart axis"],
    )
    prompt = compile_structured_prompt(structured, slide_number=1, mode="slide_render")
    assert "Type:" not in prompt
    assert "#Slide1" in prompt
    assert "## SaaS主要KPIの定義と計算式" in prompt


def test_research_mode_default_is_text_without_explicit_image_instruction() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="資料調査",
            search_mode="text_search",
            query_hints=["medieval armor reference"],
            priority="high",
            expected_output="要点を整理",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(tasks, "中世の史実を調査して")
    assert normalized[0].search_mode == "text_search"


def test_research_mode_remains_text_even_when_explicitly_requested() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="視覚方針調査",
            search_mode="text_search",
            query_hints=["sleep relaxation illustration"],
            priority="high",
            expected_output="要点を整理",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(tasks, "睡眠リラックスの参照画像を集めて")
    assert normalized[0].search_mode == "text_search"


def test_research_mode_does_not_promote_to_image_when_explicit_request_exists() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="背景調査",
            search_mode="text_search",
            query_hints=["medieval life facts"],
            priority="high",
            expected_output="事実整理",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(tasks, "中世の参照画像も収集して")
    assert normalized[0].search_mode == "text_search"


def test_research_mode_ignores_non_text_preference() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="ビジュアル参考探索",
            search_mode="text_search",
            query_hints=["wellness style board"],
            priority="high",
            expected_output="参照画像一覧",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(
        tasks,
        "ウェルネスデザインの方向性を調査",
        preferred_mode="unknown_mode",
    )
    assert normalized[0].search_mode == "text_search"


def test_research_mode_prefers_step_text_mode_even_if_task_requests_image() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="市場調査",
            search_mode="text_search",
            query_hints=["fitness market size"],
            priority="high",
            expected_output="市場規模の根拠",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(
        tasks,
        "フィットネス市場のファクト調査",
        preferred_mode="text_search",
    )
    assert normalized[0].search_mode == "text_search"


def test_writer_mode_is_constrained_by_product_type() -> None:
    assert _resolve_writer_mode("comic_script", "comic") == "comic_script"
    assert _resolve_writer_mode("story_framework", "slide") == "slide_outline"
    assert _resolve_writer_mode(None, "comic") == "story_framework"


def test_resolve_step_dependency_context_reads_research_artifacts_by_depends_on() -> None:
    state = {
        "plan": [
            {"id": 1, "capability": "researcher", "mode": "text_search", "status": "completed"},
            {"id": 2, "capability": "writer", "mode": "slide_outline", "status": "in_progress"},
        ],
        "artifacts": {
            "step_1_research_1": json.dumps(
                {
                    "task_id": 1,
                    "perspective": "市場調査",
                    "report": "A" * 3200,
                    "sources": ["https://example.com/source"],
                },
                ensure_ascii=False,
            )
        },
    }
    current_step = {
        "id": 2,
        "capability": "writer",
        "mode": "slide_outline",
        "inputs": ["research:market_facts"],
        "depends_on": [1],
    }

    context = resolve_step_dependency_context(state, current_step)
    assert context["depends_on_step_ids"] == [1]
    assert context["planned_inputs"] == ["research:market_facts"]
    assert len(context["resolved_research_inputs"]) == 1
    report = context["resolved_research_inputs"][0]["content"]["report"]
    assert isinstance(report, str)
    assert report.endswith("(truncated)")


def test_resolve_step_dependency_context_falls_back_to_research_labels_without_depends_on() -> None:
    state = {
        "plan": [
            {"id": 1, "capability": "researcher", "mode": "text_search", "status": "completed"},
            {"id": 2, "capability": "visualizer", "mode": "slide_render", "status": "in_progress"},
        ],
        "artifacts": {
            "step_1_research_1": json.dumps(
                {
                    "task_id": 1,
                    "perspective": "参考情報",
                    "search_mode": "text_search",
                    "sources": ["https://example.com/image.png"],
                },
                ensure_ascii=False,
            )
        },
    }
    current_step = {
        "id": 2,
        "capability": "visualizer",
        "mode": "slide_render",
        "inputs": ["research:reference_facts"],
        "depends_on": [],
    }

    context = resolve_step_dependency_context(state, current_step)
    assert context["depends_on_step_ids"] == []
    assert len(context["resolved_research_inputs"]) == 1
