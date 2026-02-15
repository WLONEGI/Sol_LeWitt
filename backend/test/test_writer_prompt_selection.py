from langchain_core.messages import HumanMessage, SystemMessage

from src.resources.prompts.template import apply_prompt_template


def _render_writer_prompt(product_type: str, mode: str | None = None) -> str:
    state = {
        "messages": [HumanMessage(content="テスト")],
        "product_type": product_type,
    }
    if mode:
        state["mode"] = mode
    messages = apply_prompt_template("writer", state)
    assert isinstance(messages[0], SystemMessage)
    return str(messages[0].content)


def test_writer_prompt_loads_slide_specific_rules() -> None:
    prompt = _render_writer_prompt("slide")
    assert "Baseline slide structure (PowerPoint basics)" in prompt
    assert "1. 表紙/タイトル" in prompt
    assert "2. アジェンダ（目次）" in prompt


def test_writer_prompt_loads_design_specific_rules() -> None:
    prompt = _render_writer_prompt("design")
    assert "Outline policy" in prompt
    assert "構成は固定しない" in prompt


def test_writer_prompt_defaults_to_story_framework_for_comic_without_mode() -> None:
    prompt = _render_writer_prompt("comic")
    assert "Mode Scope: story_framework" in prompt
    assert "Mode Scope: character_sheet" not in prompt
    assert "Mode Scope: comic_script" not in prompt


def test_writer_prompt_loads_comic_story_framework_mode_file() -> None:
    prompt = _render_writer_prompt("comic", mode="story_framework")
    assert "Mode Scope: story_framework" in prompt
    assert "Mode Scope: character_sheet" not in prompt
    assert "Mode Scope: comic_script" not in prompt


def test_writer_prompt_loads_comic_character_sheet_mode_file() -> None:
    prompt = _render_writer_prompt("comic", mode="character_sheet")
    assert "Mode Scope: character_sheet" in prompt
    assert "Mode Scope: story_framework" not in prompt


def test_writer_prompt_loads_comic_script_mode_file() -> None:
    prompt = _render_writer_prompt("comic", mode="comic_script")
    assert "Mode Scope: comic_script" in prompt
    assert "Mode Scope: story_framework" not in prompt
