from langchain_core.messages import HumanMessage, SystemMessage

from src.resources.prompts.template import apply_prompt_template


def _render_writer_prompt(product_type: str) -> str:
    state = {
        "messages": [HumanMessage(content="テスト")],
        "product_type": product_type,
    }
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


def test_writer_prompt_loads_comic_specific_rules() -> None:
    prompt = _render_writer_prompt("comic")
    assert "Explicit 3 Tasks" in prompt
    assert "Each mode must return its own JSON schema independently." in prompt

