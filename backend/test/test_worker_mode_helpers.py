from src.core.workflow.nodes.researcher import (
    _build_image_candidates,
    _contains_explicit_image_request,
    _extract_urls,
    _normalize_task_modes_by_instruction,
)
from src.shared.schemas.outputs import ResearchTask
from src.core.workflow.nodes.visualizer import _resolve_asset_unit_meta, _writer_output_to_slides


def test_extract_urls_and_image_candidates() -> None:
    text = "ref https://example.com/a.png and https://example.com/page"
    urls = _extract_urls(text)
    assert "https://example.com/a.png" in urls
    candidates = _build_image_candidates(urls, "image_search")
    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://example.com/a.png"
    assert candidates[0]["license_note"]
    assert "manual verification" in candidates[0]["license_note"].lower()
    assert isinstance(candidates[0]["caption"], str) and candidates[0]["caption"]


def test_image_candidate_license_note_is_domain_aware() -> None:
    urls = ["https://images.unsplash.com/photo-12345?auto=format"]
    candidates = _build_image_candidates(urls, "image_search")
    assert len(candidates) == 1
    assert candidates[0]["source_url"] == "https://images.unsplash.com/photo-12345"
    assert "unsplash license" in candidates[0]["license_note"].lower()


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
    assert slides[0]["bullet_points"][0] == "城下町の朝"


def test_resolve_asset_unit_meta_by_mode() -> None:
    unit_id, unit_kind, unit_index = _resolve_asset_unit_meta(
        mode="document_layout_render",
        product_type="document_design",
        slide_number=3,
    )
    assert unit_id == "page:3"
    assert unit_kind == "page"
    assert unit_index == 3


def test_research_mode_default_is_text_without_explicit_image_instruction() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="資料調査",
            search_mode="image_search",
            query_hints=["medieval armor reference"],
            priority="high",
            expected_output="画像候補を列挙",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(tasks, "中世の史実を調査して")
    assert normalized[0].search_mode == "text_search"


def test_research_mode_keeps_image_when_explicitly_requested() -> None:
    tasks = [
        ResearchTask(
            id=1,
            perspective="参照画像収集",
            search_mode="image_search",
            query_hints=["sleep relaxation illustration"],
            priority="high",
            expected_output="画像候補を列挙",
        )
    ]
    normalized = _normalize_task_modes_by_instruction(tasks, "睡眠リラックスの参照画像を集めて")
    assert normalized[0].search_mode == "image_search"


def test_research_mode_promotes_first_task_to_image_when_explicit_request_exists() -> None:
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
    assert normalized[0].search_mode == "image_search"


def test_contains_explicit_image_request_detects_japanese_and_english() -> None:
    assert _contains_explicit_image_request("参照画像を探して") is True
    assert _contains_explicit_image_request("Collect reference images for style") is True
    assert _contains_explicit_image_request("市場規模を調査して") is False
