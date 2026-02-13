import json
import logging
import re
from typing import Any
from typing import Literal

from langchain_core.callbacks.manager import adispatch_custom_event
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.core.workflow.state import State
from src.infrastructure.llm.llm import astream_with_retry, get_llm_by_type
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
    resolve_asset_bindings_for_step,
    resolve_step_dependency_context,
    resolve_selected_assets_for_step,
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

WRITER_ALLOWED_MODES_BY_PRODUCT: dict[str, set[str]] = {
    "slide": {"slide_outline", "infographic_spec"},
    "design": {"slide_outline"},
    "comic": {"story_framework", "character_sheet", "comic_script"},
}

WRITER_DEFAULT_MODE_BY_PRODUCT: dict[str, str] = {
    "slide": "slide_outline",
    "design": "slide_outline",
    "comic": "story_framework",
}

_CONCRETE_DATA_PATTERN = re.compile(
    r"(?:\d|%|％|円|ドル|件|社|人|年|月|日|週|四半期|Q[1-4]|前年比|YoY|CAGR|シェア|順位|TOP)",
    re.IGNORECASE,
)
_TITLE_LIKE_KEYWORDS: tuple[str, ...] = (
    "表紙",
    "タイトル",
    "アジェンダ",
    "目次",
    "agenda",
    "title",
)


def _default_writer_mode(product_type: str | None) -> str:
    return WRITER_DEFAULT_MODE_BY_PRODUCT.get(str(product_type), "slide_outline")


def _resolve_writer_mode(raw_mode: str | None, product_type: str | None) -> str:
    normalized_mode = str(raw_mode or "").strip()
    default_mode = _default_writer_mode(product_type)

    if not normalized_mode:
        return default_mode

    # Backward compatibility:
    # design plans may still request document_blueprint; normalize to slide_outline.
    if str(product_type) == "design" and normalized_mode == "document_blueprint":
        return "slide_outline"

    if normalized_mode not in WRITER_MODE_TO_SCHEMA:
        logger.warning("Writer received unknown mode '%s'. Falling back to %s.", normalized_mode, default_mode)
        return default_mode

    allowed_modes = WRITER_ALLOWED_MODES_BY_PRODUCT.get(str(product_type))
    if allowed_modes and normalized_mode not in allowed_modes:
        logger.warning(
            "Writer mode '%s' is not allowed for product_type='%s'. Falling back to %s.",
            normalized_mode,
            product_type,
            default_mode,
        )
        return default_mode

    return normalized_mode


def _slide_is_title_like(slide: Any) -> bool:
    slide_number = getattr(slide, "slide_number", None)
    if isinstance(slide_number, int) and slide_number <= 1:
        return True

    title = str(getattr(slide, "title", "") or "").strip().lower()
    if not title:
        return False
    return any(keyword in title for keyword in _TITLE_LIKE_KEYWORDS)


def _contains_concrete_data(text: str) -> bool:
    return bool(_CONCRETE_DATA_PATTERN.search(text))


def _slide_outline_density_issues(writer_output: WriterSlideOutlineOutput) -> list[str]:
    issues: list[str] = []
    slides = getattr(writer_output, "slides", None)
    if not isinstance(slides, list) or not slides:
        return ["slides が空のため、情報密度を評価できません。"]

    for slide in slides:
        if _slide_is_title_like(slide):
            continue

        slide_number = getattr(slide, "slide_number", None)
        bullets = getattr(slide, "bullet_points", None)
        bullet_items = bullets if isinstance(bullets, list) else []
        if len(bullet_items) < 3:
            issues.append(f"slide {slide_number}: bullet_points が3項目未満です。")

        parts: list[str] = [
            str(getattr(slide, "title", "") or ""),
            str(getattr(slide, "description", "") or ""),
            str(getattr(slide, "key_message", "") or ""),
            *[str(item) for item in bullet_items if isinstance(item, str)],
        ]
        if not _contains_concrete_data(" ".join(parts)):
            issues.append(f"slide {slide_number}: 具体データ（数値/比較軸/単位）が不足しています。")

    return issues


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

    mode = _resolve_writer_mode(current_step.get("mode"), state.get("product_type"))
    schema = WRITER_MODE_TO_SCHEMA.get(mode, WriterSlideOutlineOutput)
    artifact_title = WRITER_MODE_TO_TITLE.get(mode, "Writer Output")

    non_pptx_attachments = [
        item
        for item in (state.get("attachments") or [])
        if isinstance(item, dict) and str(item.get("kind") or "").lower() != "pptx"
    ]
    dependency_context = resolve_step_dependency_context(state, current_step)
    selected_step_assets = resolve_selected_assets_for_step(state, current_step.get("id"))
    selected_asset_bindings = resolve_asset_bindings_for_step(state, current_step.get("id"))

    context_payload = {
        "product_type": state.get("product_type"),
        "mode": mode,
        "instruction": current_step.get("instruction"),
        "success_criteria": current_step.get("success_criteria") or current_step.get("validation") or [],
        "target_scope": current_step.get("target_scope"),
        "planned_inputs": dependency_context["planned_inputs"],
        "depends_on_step_ids": dependency_context["depends_on_step_ids"],
        "resolved_dependency_artifacts": dependency_context["resolved_dependency_artifacts"],
        "resolved_research_inputs": dependency_context["resolved_research_inputs"],
        "selected_step_assets": selected_step_assets,
        "selected_asset_bindings": selected_asset_bindings,
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
        async for chunk in astream_with_retry(
            lambda: llm.astream(messages, config=stream_config),
            operation_name="writer.astream",
        ):
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

        if (
            state.get("product_type") == "slide"
            and mode == "slide_outline"
            and isinstance(writer_output, WriterSlideOutlineOutput)
        ):
            density_issues = _slide_outline_density_issues(writer_output)
            if density_issues:
                logger.warning(
                    "Writer slide_outline density gate triggered. Retrying once. issues=%s",
                    density_issues,
                )
                quality_gate_payload = {
                    "quality_gate": "slide_information_density",
                    "issues": density_issues,
                    "required_actions": [
                        "非タイトルスライドの bullet_points を3〜6項目にする",
                        "各非タイトルスライドに具体データ（数値・比較軸・単位）を最低1つ含める",
                        "主張と根拠の対応が分かる description / key_message にする",
                    ],
                }
                try:
                    repaired_output = await run_structured_output(
                        llm=llm,
                        schema=WriterSlideOutlineOutput,
                        messages=[
                            *messages,
                            HumanMessage(
                                content=json.dumps(quality_gate_payload, ensure_ascii=False, indent=2),
                                name="quality_gate",
                            ),
                        ],
                        config=stream_config,
                        repair_hint="Improve information density for slide_outline while keeping strict JSON schema.",
                    )
                    repaired_issues = _slide_outline_density_issues(repaired_output)
                    if repaired_issues:
                        logger.warning(
                            "Writer slide_outline density gate still reports issues after retry: %s",
                            repaired_issues,
                        )
                    writer_output = repaired_output
                except Exception as quality_error:
                    logger.warning("Writer density retry failed. Continue with original output: %s", quality_error)

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
