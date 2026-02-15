from langchain_core.messages import HumanMessage, SystemMessage

from src.resources.prompts.template import apply_prompt_template


def _render_visualizer_prompt(product_type: str, mode: str | None = None) -> str:
    state = {
        "messages": [HumanMessage(content="テスト")],
        "product_type": product_type,
    }
    if mode:
        state["mode"] = mode
    messages = apply_prompt_template("visualizer_prompt", state)
    assert isinstance(messages[0], SystemMessage)
    return str(messages[0].content)


def test_visualizer_prompt_loads_comic_layout_freedom_rules() -> None:
    prompt = _render_visualizer_prompt("comic", mode="comic_page_render")
    assert "Mode Directive: comic_page_render" in prompt
    assert "avoid repetitive uniform four-panel vertical split as a default" in prompt.lower()
    assert "Controlled frame-break is allowed" in prompt


def test_visualizer_prompt_loads_character_sheet_mode_file() -> None:
    prompt = _render_visualizer_prompt("comic", mode="character_sheet_render")
    assert "Mode Directive: character_sheet_render" in prompt
    assert "Render in full color" in prompt


def test_visualizer_prompt_defaults_to_comic_page_render_without_mode() -> None:
    prompt = _render_visualizer_prompt("comic")
    assert "Mode Directive: comic_page_render" in prompt
    assert "Mode Directive: character_sheet_render" not in prompt
