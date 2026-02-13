from langchain_core.messages import HumanMessage, SystemMessage

from src.resources.prompts.template import apply_prompt_template


def _render_planner_prompt(product_type: str) -> str:
    state = {
        "messages": [HumanMessage(content="テスト")],
        "product_type": product_type,
        "request_intent": "new",
        "planning_mode": "create",
        "latest_user_text": "テスト",
        "plan": "[]",
        "plan_execution_snapshot": "{\"total\":0,\"pending\":0,\"in_progress\":0,\"completed\":0,\"blocked\":0}",
        "unfinished_steps": "[]",
        "target_scope": "{}",
        "interrupt_intent": "false",
        "attachment_signal": "{\"has_pptx_attachment\":false,\"attachment_count\":0,\"pptx_attachment_count\":0,\"pptx_context_template_count\":0,\"attachments_summary\":[]}",
        "has_pptx_attachment": "false",
        "pptx_attachment_count": "0",
        "pptx_context_template_count": "0",
    }
    messages = apply_prompt_template("planner", state)
    assert isinstance(messages[0], SystemMessage)
    return str(messages[0].content)


def test_planner_prompt_loads_slide_specific_rules() -> None:
    prompt = _render_planner_prompt("slide")
    assert "Product Guidance: slide" in prompt
    assert "Researcher should be inserted by default." in prompt
    assert "PPTX template policy (mandatory)" in prompt
    assert "mode must be `pptx_slides_to_images` only." in prompt


def test_planner_prompt_loads_design_specific_rules() -> None:
    prompt = _render_planner_prompt("design")
    assert "Product Guidance: design" in prompt
    assert "researcher (`text_search`) as first candidate" in prompt


def test_planner_prompt_loads_comic_specific_rules() -> None:
    prompt = _render_planner_prompt("comic")
    assert "Product Guidance: comic" in prompt
    assert "`character_sheet_render` must depend on `character_sheet`." in prompt


def test_planner_prompt_contains_single_turn_create_policy() -> None:
    prompt = _render_planner_prompt("slide")
    assert "Planning Policy (Important)" in prompt
    assert "`planning_mode` is always `create`." in prompt
