import asyncio
import json

from src.core.workflow.nodes.common import resolve_step_dependency_context
from src.core.workflow.nodes.researcher import (
    _extract_urls,
    _normalize_task_modes_by_instruction,
)
from src.shared.schemas.outputs import ImagePrompt, ResearchTask, StructuredImagePrompt
from src.core.workflow.nodes.visualizer import (
    _append_reference_guidance,
    _build_character_sheet_prompt_text,
    _build_comic_page_prompt_text,
    _extract_pptx_slide_reference_assets,
    _find_latest_character_sheet_render_urls,
    _is_pptx_processing_asset,
    _is_pptx_processing_dependency_artifact,
    _plan_visual_asset_usage,
    _prompt_item_to_output_payload,
    _selector_asset_summary,
    _selector_unit_summary,
    _resolve_image_generation_prompt,
    _resolve_asset_unit_meta,
    _summarize_source_master_layout_meta,
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


def test_comic_page_prompt_includes_character_sheet_anchors() -> None:
    writer_data = {
        "pages": [
            {
                "page_number": 1,
                "page_goal": "導入",
                "panels": [
                    {"panel_number": 1, "foreground": "主人公が走る", "background": "夜の路地"},
                ],
            }
        ]
    }
    character_sheet_data = {
        "characters": [
            {
                "name": "アオイ",
                "story_role": "主人公",
                "face_hair_anchors": "右分けの短髪",
                "costume_anchors": "長いコート",
                "silhouette_signature": "片肩バッグ",
                "color_palette": {"main": "#112233", "sub": "#445566", "accent": "#778899"},
                "signature_items": ["古い時計"],
                "forbidden_drift": ["髪型変更禁止"],
            }
        ]
    }
    prompt = _build_comic_page_prompt_text(
        slide_number=1,
        slide_content={"description": "導入"},
        writer_data=writer_data,
        character_sheet_data=character_sheet_data,
    )
    assert "[Character Sheet Anchors]" in prompt
    assert "アオイ (主人公)" in prompt
    assert "Face/Hair anchors: 右分けの短髪" in prompt
    assert "Forbidden drift: 髪型変更禁止" in prompt
    assert "[Render Policy]" in prompt
    assert "[Panel Layout Policy]" in prompt
    assert "Avoid defaulting to a uniform four-panel vertical split." in prompt
    assert "Controlled frame-break is allowed" in prompt
    assert "[Mode Prompt]" in prompt
    assert "Mode Directive: comic_page_render" in prompt
    assert "masterpiece, best quality, cinematic black and white manga panel illustration," in prompt
    assert "smooth and balanced grayscale shading (no screentone, no halftone pattern)," in prompt
    assert "strict black-and-white manga page" not in prompt


def test_comic_page_prompt_without_panels_adds_default_marker() -> None:
    writer_data = {
        "pages": [
            {
                "page_number": 1,
                "page_goal": "導入",
                "panels": [],
            }
        ]
    }
    prompt = _build_comic_page_prompt_text(
        slide_number=1,
        slide_content={"description": "導入", "bullet_points": []},
        writer_data=writer_data,
        character_sheet_data=None,
    )
    assert "[Panels]" in prompt
    assert "- 未指定" in prompt


def test_character_sheet_prompt_uses_monochrome_render_policy() -> None:
    prompt = _build_character_sheet_prompt_text(
        slide_number=1,
        slide_content={"character_profile": {"name": "アオイ"}},
        writer_data={
            "characters": [
                {
                    "name": "アオイ",
                    "story_role": "主人公",
                    "core_personality": "責任感が強い",
                    "motivation": "仲間を守る",
                    "weakness_or_fear": "孤立",
                    "silhouette_signature": "長いコート",
                    "face_hair_anchors": "右分け短髪",
                    "costume_anchors": "濃色コート",
                    "color_palette": {"main": "#112233", "sub": "#445566", "accent": "#778899"},
                }
            ]
        },
        story_framework_data={},
        layout_template_enabled=False,
        assigned_assets=None,
    )
    assert "[Render Policy]" in prompt
    assert "masterpiece, best quality, cinematic black and white manga panel illustration," in prompt
    assert "pure black, pure white, and soft gray tones only (no texture noise, no color)," in prompt
    assert "Color palette:" not in prompt


def test_find_latest_character_sheet_render_urls_prefers_latest_character_visual() -> None:
    artifacts = {
        "step_2_visual": json.dumps(
            {
                "product_type": "comic",
                "mode": "comic_page_render",
                "comic_pages": [
                    {
                        "page_number": 1,
                        "generated_image_url": "https://example.com/comic-1.png",
                    }
                ]
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
                        "generated_image_url": "https://example.com/char-latest-1.png",
                    },
                    {
                        "character_number": 2,
                        "generated_image_url": "https://example.com/char-latest-2.png",
                    },
                ]
            },
            ensure_ascii=False,
        ),
        "step_1_visual": json.dumps(
            {
                "product_type": "comic",
                "mode": "character_sheet_render",
                "characters": [
                    {
                        "character_number": 1,
                        "generated_image_url": "https://example.com/char-old-1.png",
                    }
                ]
            },
            ensure_ascii=False,
        ),
    }

    urls = _find_latest_character_sheet_render_urls(artifacts)
    assert urls == [
        "https://example.com/char-latest-1.png",
        "https://example.com/char-latest-2.png",
    ]


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
    )
    prompt = compile_structured_prompt(structured, slide_number=1, mode="slide_render")
    assert "Type:" not in prompt
    assert "Presentation Slide" in prompt
    assert "# SaaS主要KPIの定義と計算式" in prompt
    assert "## 経営判断に必要な共通指標" in prompt
    assert "### 経営判断に必要な共通指標" not in prompt
    assert "Text policy: render_all_text" not in prompt
    assert "Render all provided text (title, subtitle, and contents) in-image without omission." not in prompt


def test_compile_structured_prompt_omits_default_text_policy_label_for_design_mode() -> None:
    structured = StructuredImagePrompt(
        slide_type="Document Page",
        main_title="ブランドガイドライン",
        sub_title="カラーとタイポグラフィ",
        contents="- Color palette\n- Font rules",
        visual_style="clean editorial layout, modern typography, white background",
    )
    prompt = compile_structured_prompt(structured, slide_number=2, mode="document_layout_render")
    assert "# Page 2 : ブランドガイドライン" in prompt
    assert "## カラーとタイポグラフィ" in prompt
    assert "### カラーとタイポグラフィ" not in prompt
    assert "Text policy: render_all_text" not in prompt
    assert "Render all provided text (title, subtitle, and contents) in-image without omission." not in prompt


def test_append_reference_guidance_adds_english_note_when_references_exist() -> None:
    base_prompt = "Presentation Slide\n# タイトル\nVisual style: clean business"
    updated = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)

    assert "[Reference Guidance]" in updated
    assert "Use attached PPTX-derived reference images as the primary design anchor." in updated
    assert updated.startswith(base_prompt)


def test_append_reference_guidance_noop_when_no_references() -> None:
    base_prompt = "Presentation Slide\n# 内容\nVisual style: modern infographic"
    updated = _append_reference_guidance(base_prompt, enable_pptx_guidance=False)

    assert updated == base_prompt


def test_append_reference_guidance_is_idempotent() -> None:
    base_prompt = "Presentation Slide\n# 比較\nVisual style: editorial"
    once = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)
    twice = _append_reference_guidance(once, enable_pptx_guidance=True)

    assert once == twice


def test_append_reference_guidance_adds_template_text_handling_when_template_reference_exists() -> None:
    base_prompt = "Presentation Slide\n# 構成\nVisual style: corporate"
    updated = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)

    assert "[Reference Guidance]" in updated
    assert "Treat any text visible in references as placeholder examples only; do not copy it." in updated


def test_append_reference_guidance_template_block_is_idempotent() -> None:
    base_prompt = "Presentation Slide\n# 施策"
    once = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)
    twice = _append_reference_guidance(once, enable_pptx_guidance=True)

    assert once == twice


def test_append_reference_guidance_adds_attachment_background_fit_note_for_slide() -> None:
    base_prompt = "Presentation Slide\n# 施策\nVisual style: clean corporate"
    updated = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)

    assert "[Reference Guidance]" in updated
    assert "nuanced and delicate alignment" in updated


def test_append_reference_guidance_attachment_background_fit_block_is_idempotent() -> None:
    base_prompt = "Presentation Slide\n# 比較"
    once = _append_reference_guidance(base_prompt, enable_pptx_guidance=True)
    twice = _append_reference_guidance(once, enable_pptx_guidance=True)

    assert once == twice


def test_compile_structured_prompt_keeps_text_policy_label_for_comic_mode() -> None:
    structured = StructuredImagePrompt(
        slide_type="Comic Page",
        main_title="序章",
        sub_title="夜明け前",
        contents="- 1コマ目\n- 2コマ目",
        visual_style="manga line art",
        text_policy="render_all_text",
        negative_constraints=["photorealistic finish"],
    )
    prompt = compile_structured_prompt(structured, slide_number=1, mode="comic_page_render")
    assert "#Page1" in prompt
    assert "Text policy: render_all_text" in prompt


def test_document_layout_resolves_prompt_from_structured_prompt() -> None:
    structured = StructuredImagePrompt(
        slide_type="Document Page",
        main_title="自治体向け交通再編",
        sub_title="実装ロードマップ",
        contents="- 施策A\n- 施策B",
        visual_style="clean editorial grid, strong hierarchy, neutral palette",
    )
    prompt_item = ImagePrompt(
        slide_number=2,
        layout_type="title_and_content",
        structured_prompt=structured,
        image_generation_prompt="legacy plain prompt should be ignored",
        rationale="test",
    )

    resolved = _resolve_image_generation_prompt(prompt_item, mode="document_layout_render")
    assert resolved.startswith("Design a single editorial document page (page 2).")
    assert "Main title: 自治体向け交通再編" in resolved
    assert "legacy plain prompt should be ignored" not in resolved


def test_slide_prompt_can_suppress_visual_style_for_template_reference() -> None:
    structured = StructuredImagePrompt(
        slide_type="Content",
        main_title="売上推移",
        sub_title="Q1-Q4",
        contents="- Q1: 100\n- Q4: 180",
        visual_style="modern clean business",
    )
    prompt_item = ImagePrompt(
        slide_number=1,
        layout_type="title_and_content",
        structured_prompt=structured,
        image_generation_prompt=None,
        rationale="test",
    )

    resolved = _resolve_image_generation_prompt(
        prompt_item,
        mode="slide_render",
        suppress_visual_style=True,
    )
    assert "Visual style:" not in resolved


def test_output_payload_omits_empty_legacy_prompt_field() -> None:
    prompt_item = ImagePrompt(
        slide_number=1,
        layout_type="title_slide",
        structured_prompt=StructuredImagePrompt(
            slide_type="Title Slide",
            main_title="再設計提案",
            sub_title=None,
            contents="- 現状\n- 提案",
            visual_style="editorial infographic",
        ),
        image_generation_prompt=None,
        compiled_prompt="Presentation Slide\n# 再設計提案",
        rationale="test",
        generated_image_url="https://example.com/image.png",
    )

    payload = _prompt_item_to_output_payload(prompt_item, title="再設計提案", selected_inputs=[])
    assert "image_generation_prompt" not in payload
    assert payload["compiled_prompt"] == "Presentation Slide\n# 再設計提案"
    assert "text_policy" not in payload["structured_prompt"]
    assert "negative_constraints" not in payload["structured_prompt"]


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
    assert _resolve_writer_mode("document_blueprint", "design") == "slide_outline"


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


def test_extract_pptx_slide_reference_assets_reads_data_analyst_metadata() -> None:
    dependency_context = {
        "resolved_dependency_artifacts": [
            {
                "artifact_id": "step_1_data",
                "producer_step_id": 1,
                "producer_capability": "data_analyst",
                "producer_mode": "pptx_slides_to_images",
                "content": {
                    "output_files": [
                        {
                            "url": "https://example.com/template_01.png",
                            "mime_type": "image/png",
                            "source_title": "交通課題の現状",
                            "source_texts": ["高齢化率 34.2%", "移動困難者 1.8万人"],
                            "source_layout_placeholders": ["title", "body"],
                            "source_master_texts": ["年度方針", "重点施策"],
                            "source_mode": "pptx_slides_to_images",
                        },
                        {
                            "url": "https://example.com/template_01.pdf",
                            "mime_type": "application/pdf",
                            "source_mode": "pptx_slides_to_images",
                        },
                    ]
                },
            }
        ]
    }

    assets = _extract_pptx_slide_reference_assets(dependency_context)

    assert len(assets) == 1
    assert assets[0]["uri"] == "https://example.com/template_01.png"
    assert assets[0]["source_title"] == "交通課題の現状"
    assert assets[0]["source_texts"] == ["高齢化率 34.2%", "移動困難者 1.8万人"]
    assert assets[0]["source_layout_placeholders"] == ["title", "body"]
    assert assets[0]["source_master_texts"] == ["年度方針", "重点施策"]
    assert assets[0]["is_pptx_slide_reference"] is True


def test_extract_pptx_slide_reference_assets_accepts_master_mode() -> None:
    dependency_context = {
        "resolved_dependency_artifacts": [
            {
                "artifact_id": "step_1_data",
                "producer_step_id": 1,
                "producer_capability": "data_analyst",
                "producer_mode": "pptx_master_to_images",
                "content": {
                    "output_files": [
                        {
                            "url": "https://example.com/master_01.png",
                            "mime_type": "image/png",
                            "source_master_name": "Corporate Master",
                            "source_master_texts": ["年度方針", "重点施策"],
                            "source_layout_placeholders": ["title", "body"],
                            "source_mode": "pptx_master_to_images",
                        }
                    ]
                },
            }
        ]
    }

    assets = _extract_pptx_slide_reference_assets(dependency_context)

    assert len(assets) == 1
    assert assets[0]["uri"] == "https://example.com/master_01.png"
    assert assets[0]["producer_mode"] == "pptx_master_to_images"
    assert assets[0]["source_mode"] == "pptx_master_to_images"
    assert assets[0]["source_master_name"] == "Corporate Master"
    assert assets[0]["source_master_texts"] == ["年度方針", "重点施策"]
    assert assets[0]["is_pptx_slide_reference"] is True


def test_is_pptx_processing_asset_detects_pptx_modes() -> None:
    assert _is_pptx_processing_asset({"producer_mode": "pptx_slides_to_images"}) is True
    assert _is_pptx_processing_asset({"source_mode": "pptx_master_to_images"}) is True
    assert _is_pptx_processing_asset({"label": "pptx_slide_reference"}) is True
    assert _is_pptx_processing_asset({"producer_mode": "slide_render"}) is False


def test_is_pptx_processing_dependency_artifact_detects_output_modes() -> None:
    artifact = {
        "producer_mode": "images_to_package",
        "content": {
            "output_value": {"mode": "pptx_slides_to_images"},
            "output_files": [{"url": "https://example.com/a.png", "source_mode": "pptx_slides_to_images"}],
        },
    }
    assert _is_pptx_processing_dependency_artifact(artifact) is True
    assert _is_pptx_processing_dependency_artifact({"producer_mode": "images_to_package", "content": {}}) is False


def test_summarize_source_master_layout_meta_from_placeholders() -> None:
    assert _summarize_source_master_layout_meta({"source_layout_placeholders": ["title"]}) == "タイトル"
    assert _summarize_source_master_layout_meta({"source_layout_placeholders": ["title", "body"]}) == "タイトル＋コンテンツ"
    assert _summarize_source_master_layout_meta({"source_layout_placeholders": ["title", "pic", "body"]}) == "コンテンツ＋絵"


def test_selector_asset_summary_for_slide_render_is_minimal() -> None:
    summary = _selector_asset_summary(
        mode="slide_render",
        asset={
            "asset_id": "asset:pptx:1",
            "is_pptx_slide_reference": True,
            "source_layout_placeholders": ["title", "pic", "body"],
            "source_master_name": "Corporate Master",
            "source_layout_name": "Title and Content",
            "source_master_texts": ["年度方針", "重点施策"],
        },
    )
    assert set(summary.keys()) == {
        "asset_id",
        "is_pptx_slide_reference",
        "source_master_layout_meta",
        "source_layout_name",
        "source_layout_placeholders",
        "source_master_name",
        "source_master_texts",
    }
    assert summary["source_master_layout_meta"] == "コンテンツ＋絵"
    assert summary["source_layout_name"] == "Title and Content"
    assert summary["source_layout_placeholders"] == ["title", "pic", "body"]
    assert summary["source_master_name"] == "Corporate Master"
    assert summary["source_master_texts"] == ["年度方針", "重点施策"]


def test_selector_unit_summary_for_slide_render_is_minimal() -> None:
    summary = _selector_unit_summary(
        mode="slide_render",
        slide={
            "slide_number": 2,
            "title": "交通課題の現状",
            "description": "移動困難者の増加と路線維持コストの上昇",
            "bullet_points": ["高齢化率 34.2%", "移動困難者 1.8万人", "高齢化率 34.2%"],
            "key_message": "持続可能な地域交通への転換が必要",
        },
    )
    assert summary == {
        "slide_number": 2,
        "content_title": "交通課題の現状",
        "content_texts": [
            "移動困難者の増加と路線維持コストの上昇",
            "持続可能な地域交通への転換が必要",
            "高齢化率 34.2%",
            "移動困難者 1.8万人",
        ],
        "target_master_layout_meta": "タイトル＋コンテンツ",
    }


def test_plan_visual_asset_usage_limits_pptx_reference_to_one_per_slide(monkeypatch) -> None:
    class _Assignment:
        def __init__(self, slide_number: int, asset_ids: list[str]) -> None:
            self.slide_number = slide_number
            self.asset_ids = asset_ids

    class _Plan:
        def __init__(self, assignments: list[_Assignment]) -> None:
            self.assignments = assignments

    async def _fake_run_structured_output(**kwargs):  # noqa: ANN003
        return _Plan(
            assignments=[
                _Assignment(slide_number=1, asset_ids=["pptx_asset_1", "pptx_asset_2", "image_asset_1"])
            ]
        )

    monkeypatch.setattr(
        "src.core.workflow.nodes.visualizer.run_structured_output",
        _fake_run_structured_output,
    )

    assignments = asyncio.run(
        _plan_visual_asset_usage(
            llm=object(),
            mode="slide_render",
            writer_slides=[
                {
                    "slide_number": 1,
                    "title": "交通課題の現状",
                    "description": "移動困難の増加",
                    "bullet_points": ["高齢化率 34.2%", "移動困難者 1.8万人"],
                }
            ],
            selected_assets=[
                {
                    "asset_id": "pptx_asset_1",
                    "uri": "https://example.com/template_01.png",
                    "is_image": True,
                    "producer_mode": "pptx_slides_to_images",
                    "is_pptx_slide_reference": True,
                },
                {
                    "asset_id": "pptx_asset_2",
                    "uri": "https://example.com/template_02.png",
                    "is_image": True,
                    "producer_mode": "pptx_slides_to_images",
                    "is_pptx_slide_reference": True,
                },
                {
                    "asset_id": "image_asset_1",
                    "uri": "https://example.com/other_ref.png",
                    "is_image": True,
                    "producer_mode": "slide_render",
                },
            ],
            instruction="Writer内容に近い参照を選んで生成する",
            config={},
        )
    )

    assert assignments[1] == ["pptx_asset_1", "image_asset_1"]
