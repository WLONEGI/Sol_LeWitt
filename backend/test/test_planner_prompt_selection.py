from langchain_core.messages import HumanMessage, SystemMessage

from src.resources.prompts.template import apply_prompt_template


def _render_planner_prompt(product_type: str) -> str:
    state = {
        "messages": [HumanMessage(content="テスト")],
        "product_type": product_type,
        "request_intent": "new",
        "planning_mode": "initial",
        "latest_user_text": "テスト",
        "plan": "[]",
    }
    messages = apply_prompt_template("planner", state)
    assert isinstance(messages[0], SystemMessage)
    return str(messages[0].content)


def test_planner_prompt_loads_slide_specific_rules() -> None:
    prompt = _render_planner_prompt("slide")
    assert "Product Guidance: slide" in prompt
    assert "Researcher should be inserted by default." in prompt


def test_planner_prompt_loads_design_specific_rules() -> None:
    prompt = _render_planner_prompt("design")
    assert "Product Guidance: design" in prompt
    assert "researcher (`image_search`) as first candidate" in prompt


def test_planner_prompt_loads_comic_specific_rules() -> None:
    prompt = _render_planner_prompt("comic")
    assert "Product Guidance: comic" in prompt
    assert "`character_sheet_render` must depend on `character_sheet`." in prompt
