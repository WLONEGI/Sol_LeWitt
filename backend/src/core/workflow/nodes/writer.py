import json
import logging
from typing import Literal

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.core.workflow.state import State
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.config import AGENT_LLM_MAP
from src.shared.schemas import (
    WriterCharacterSheetOutput,
    WriterComicScriptOutput,
    WriterDocumentBlueprintOutput,
    WriterInfographicSpecOutput,
    WriterSlideOutlineOutput,
    WriterStoryFrameworkOutput,
)

from .common import (
    build_worker_error_payload,
    create_worker_response,
    extract_first_json,
    run_structured_output,
    split_content_parts,
)

logger = logging.getLogger(__name__)

WRITER_MODE_TO_SCHEMA = {
    "slide_outline": WriterSlideOutlineOutput,
    "story_framework": WriterStoryFrameworkOutput,
    "character_sheet": WriterCharacterSheetOutput,
    "infographic_spec": WriterInfographicSpecOutput,
    "document_blueprint": WriterDocumentBlueprintOutput,
    "comic_script": WriterComicScriptOutput,
}

WRITER_MODE_TO_TITLE = {
    "slide_outline": "Slide Outline",
    "story_framework": "Story Framework",
    "character_sheet": "Character Sheet",
    "infographic_spec": "Infographic Spec",
    "document_blueprint": "Document Blueprint",
    "comic_script": "Comic Script",
}
WRITER_MODE_TO_ARTIFACT_TYPE = {
    "slide_outline": "outline",
    "story_framework": "writer_story_framework",
    "character_sheet": "writer_character_sheet",
    "infographic_spec": "writer_infographic_spec",
    "document_blueprint": "writer_document_blueprint",
    "comic_script": "writer_comic_script",
}


def _default_writer_mode(product_type: str | None) -> str:
    if product_type == "comic":
        return "comic_script"
    if product_type == "document_design":
        return "document_blueprint"
    return "slide_outline"


async def writer_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """
    Writer worker node.
    """
    logger.info("Writer starting task")

    try:
        step_index, current_step = next(
            (i, step)
            for i, step in enumerate(state["plan"])
            if step.get("status") == "in_progress"
            and step.get("capability") == "writer"
        )
    except StopIteration:
        logger.error("Writer called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    mode = str(current_step.get("mode") or _default_writer_mode(state.get("product_type")))
    schema = WRITER_MODE_TO_SCHEMA.get(mode, WriterSlideOutlineOutput)
    artifact_title = WRITER_MODE_TO_TITLE.get(mode, "Writer Output")

    non_pptx_attachments = [
        item
        for item in (state.get("attachments") or [])
        if isinstance(item, dict) and str(item.get("kind") or "").lower() != "pptx"
    ]

    context_payload = {
        "mode": mode,
        "instruction": current_step.get("instruction"),
        "success_criteria": current_step.get("success_criteria") or current_step.get("validation") or [],
        "target_scope": current_step.get("target_scope"),
        "selected_image_inputs": state.get("selected_image_inputs") or [],
        "attachments": non_pptx_attachments,
        "available_artifacts": state.get("artifacts", {}),
    }

    messages = apply_prompt_template("writer", state)
    messages.append(
        HumanMessage(
            content=json.dumps(context_payload, ensure_ascii=False, indent=2),
            name="supervisor",
        )
    )

    llm = get_llm_by_type(AGENT_LLM_MAP["writer"])

    try:
        stream_config = config.copy()
        stream_config["run_name"] = "writer"

        full_text = ""
        async for chunk in llm.astream(messages, config=stream_config):
            if not getattr(chunk, "content", None):
                continue
            _, text = split_content_parts(chunk.content)
            if text:
                full_text += text

        try:
            json_text = extract_first_json(full_text) or full_text
            writer_output = schema.model_validate_json(json_text)
        except Exception as parse_error:
            logger.warning("Writer streaming JSON parse failed: %s. Falling back to repair.", parse_error)
            writer_output = await run_structured_output(
                llm=llm,
                schema=schema,
                messages=messages,
                config=stream_config,
                repair_hint=f"Schema: {schema.__name__}. No extra text.",
            )

        execution_summary = getattr(writer_output, "execution_summary", f"{mode} を生成しました。")
        if mode == "slide_outline" and hasattr(writer_output, "slides"):
            execution_summary = f"{execution_summary}（{len(getattr(writer_output, 'slides', []))}枚）"

        user_message = getattr(writer_output, "user_message", None)
        result_summary = (
            str(user_message).strip()
            if isinstance(user_message, str) and user_message.strip()
            else execution_summary
        )

        content_json = writer_output.model_dump_json(exclude_none=True)
        artifact_id = f"step_{current_step['id']}_story"
        artifact_type = WRITER_MODE_TO_ARTIFACT_TYPE.get(mode, "report")
        state["plan"][step_index]["result_summary"] = execution_summary

        try:
            await adispatch_custom_event(
                "writer-output",
                {
                    "artifact_id": artifact_id,
                    "title": artifact_title,
                    "artifact_type": artifact_type,
                    "mode": mode,
                    "status": "completed",
                    "output": writer_output.model_dump(exclude_none=True),
                },
                config=config,
            )
        except Exception as dispatch_error:
            logger.warning("Failed to dispatch writer-output: %s", dispatch_error)

        return create_worker_response(
            role="writer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step["id"],
            state=state,
            artifact_key_suffix="story",
            artifact_title=artifact_title,
            artifact_icon="FileText",
            capability="writer",
            emitter_name="writer",
        )
    except Exception as e:
        logger.error("Writer output failed: %s", e)
        content_json = build_worker_error_payload(
            error_text=str(e),
            failed_checks=["worker_execution"],
        )
        result_summary = f"Error: {str(e)}"
        state["plan"][step_index]["result_summary"] = result_summary

        try:
            await adispatch_custom_event(
                "writer-output",
                {
                    "artifact_id": f"step_{current_step['id']}_story",
                    "title": artifact_title,
                    "artifact_type": WRITER_MODE_TO_ARTIFACT_TYPE.get(mode, "report"),
                    "mode": mode,
                    "status": "failed",
                    "output": json.loads(content_json),
                },
                config=config,
            )
        except Exception as dispatch_error:
            logger.warning("Failed to dispatch writer-output (error): %s", dispatch_error)

        return create_worker_response(
            role="writer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step["id"],
            state=state,
            artifact_key_suffix="story",
            artifact_title=artifact_title,
            is_error=True,
            capability="writer",
            emitter_name="writer",
        )
