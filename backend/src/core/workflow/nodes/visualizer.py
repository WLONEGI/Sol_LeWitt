import logging
import json
import random
import asyncio
import re
import hashlib
from pathlib import Path
from typing import Literal, Any
from pydantic import BaseModel, Field

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command

from src.shared.config.settings import settings
from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import (
    VisualizerOutput,
    VisualizerPlan,
    ImagePrompt,
    GenerationConfig,
    StructuredImagePrompt,
    ThoughtSignature
)
from src.core.workflow.state import State

# Updated Imports for Services
from src.domain.designer.generator import generate_image, create_image_chat_session_async, send_message_for_image_async
from src.infrastructure.storage.gcs import upload_to_gcs, download_blob_as_bytes

from .common import (
    build_worker_error_payload,
    create_worker_response,
    resolve_asset_bindings_for_step,
    resolve_step_dependency_context,
    resolve_selected_assets_for_step,
    run_structured_output,
)

logger = logging.getLogger(__name__)

ASPECT_RATIO_BY_MODE = {
    "slide_render": "16:9",
    "document_layout_render": "4:5",
    "comic_page_render": "9:16",
    "character_sheet_render": "2:3",
    "story_framework_render": "16:9",
}

CHARACTER_SHEET_TEMPLATE_ID = "local://character_sheet_layout_reference.png"
CHARACTER_SHEET_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[3]
    / "resources"
    / "templates"
    / "character_sheet_layout_reference.png"
)

ASPECT_RATIO_HINTS = {
    "16:9": ("16:9", "横長", "landscape"),
    "1:1": ("1:1", "正方形", "square"),
    "2:3": ("2:3",),
    "4:5": ("4:5",),
    "3:4": ("3:4",),
    "9:16": ("9:16", "縦長", "vertical"),
}
# Upper bound for reference images passed to one generation request.
MAX_VISUAL_REFERENCES_PER_UNIT = 14
MAX_MANDATORY_CHARACTER_SHEET_REFERENCES = 14
CHARACTER_PROMPT_HEADER_PATTERN = re.compile(r"^\s*#Character\d+\b", re.IGNORECASE)
PROMPT_LOG_PREVIEW_MAX_CHARS = 2000
REFERENCE_GUIDANCE_HEADER = "[Reference Guidance]"
REFERENCE_GUIDANCE_TEXT = (
    "Use attached reference image(s) as strong guidance for visual style, composition, and color palette. "
    "Keep the final output faithful to the requested content and text intent."
)
TEMPLATE_TEXT_HANDLING_HEADER = "[Template Text Handling]"
TEMPLATE_TEXT_HANDLING_TEXT = (
    "Treat any text visible in template/reference images as placeholder examples only. "
    "Do not copy or preserve template sample text. "
    "Render only the current slide's provided title, subtitle, and contents."
)


class VisualAssetUnitSelection(BaseModel):
    slide_number: int = Field(description="対象スライドまたはページ番号")
    asset_ids: list[str] = Field(default_factory=list, description="参照に使うasset_id一覧")


class VisualAssetUsagePlan(BaseModel):
    assignments: list[VisualAssetUnitSelection] = Field(default_factory=list, description="単位ごとの参照割当")

def _safe_json_loads(value: Any) -> Any | None:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    if isinstance(value, dict):
        return value
    return None


def _log_prompt_preview(value: str | None, *, max_chars: int = PROMPT_LOG_PREVIEW_MAX_CHARS) -> str:
    if not isinstance(value, str):
        return "null"
    normalized = value.replace("\r", "\\r").replace("\n", "\\n").strip()
    if not normalized:
        return "<empty>"
    if len(normalized) > max_chars:
        return f"{normalized[:max_chars]}...(truncated)"
    return normalized


def _append_reference_guidance(
    prompt_text: str,
    *,
    has_references: bool,
    has_template_references: bool = False,
) -> str:
    base = (prompt_text or "").rstrip()
    sections: list[str] = []

    if has_references and REFERENCE_GUIDANCE_HEADER not in base:
        sections.append(f"{REFERENCE_GUIDANCE_HEADER}\n{REFERENCE_GUIDANCE_TEXT}")

    if has_template_references and TEMPLATE_TEXT_HANDLING_HEADER not in base:
        sections.append(f"{TEMPLATE_TEXT_HANDLING_HEADER}\n{TEMPLATE_TEXT_HANDLING_TEXT}")

    if not sections:
        return prompt_text
    if base:
        return f"{base}\n\n" + "\n\n".join(sections)
    return "\n\n".join(sections)


def _is_image_asset(asset: dict[str, Any]) -> bool:
    if bool(asset.get("is_image")):
        return True
    uri = str(asset.get("uri") or "").lower()
    mime_type = str(asset.get("mime_type") or "").lower()
    return mime_type.startswith("image/") or uri.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"))


def _asset_summary(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": asset.get("asset_id"),
        "source_type": asset.get("source_type"),
        "mime_type": asset.get("mime_type"),
        "uri": asset.get("uri"),
        "label": asset.get("label"),
        "title": asset.get("title"),
        "producer_step_id": asset.get("producer_step_id"),
        "producer_capability": asset.get("producer_capability"),
        "producer_mode": asset.get("producer_mode"),
        "source_mode": asset.get("source_mode"),
        "source_title": asset.get("source_title"),
        "source_texts": (
            asset.get("source_texts")
            if isinstance(asset.get("source_texts"), list)
            else []
        ),
        "source_layout_name": asset.get("source_layout_name"),
        "source_layout_placeholders": (
            asset.get("source_layout_placeholders")
            if isinstance(asset.get("source_layout_placeholders"), list)
            else []
        ),
        "source_master_name": asset.get("source_master_name"),
        "source_master_texts": (
            asset.get("source_master_texts")
            if isinstance(asset.get("source_master_texts"), list)
            else []
        ),
        "is_pptx_slide_reference": bool(asset.get("is_pptx_slide_reference")),
    }


def _is_pptx_slide_reference_asset(asset: dict[str, Any]) -> bool:
    if bool(asset.get("is_pptx_slide_reference")):
        return True
    if str(asset.get("producer_mode") or "").strip().lower() in {"pptx_slides_to_images", "pptx_master_to_images"}:
        return True
    if str(asset.get("source_mode") or "").strip().lower() in {"pptx_slides_to_images", "pptx_master_to_images"}:
        return True
    return False


def _is_template_reference_asset(asset: dict[str, Any]) -> bool:
    if _is_pptx_slide_reference_asset(asset):
        return True
    role_hints = asset.get("role_hints")
    if isinstance(role_hints, list):
        lowered_hints = {str(item).strip().lower() for item in role_hints if isinstance(item, str)}
        if {"layout_reference", "template_source"} & lowered_hints:
            return True
    label = str(asset.get("label") or "").strip().lower()
    return label == "pptx_slide_reference"


def _extract_pptx_slide_reference_assets(
    dependency_context: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_dependencies = (dependency_context or {}).get("resolved_dependency_artifacts")
    if not isinstance(raw_dependencies, list):
        return []

    output: list[dict[str, Any]] = []
    seen_by_uri: set[str] = set()

    for dependency in raw_dependencies:
        if not isinstance(dependency, dict):
            continue
        if str(dependency.get("producer_capability") or "").strip().lower() != "data_analyst":
            continue

        producer_mode = str(dependency.get("producer_mode") or "").strip().lower()
        content = dependency.get("content")
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                continue
        if not isinstance(content, dict):
            continue

        output_files = content.get("output_files")
        if not isinstance(output_files, list):
            continue

        for item in output_files:
            if not isinstance(item, dict):
                continue
            uri = str(item.get("url") or "").strip()
            if not uri or uri in seen_by_uri:
                continue
            mime_type = str(item.get("mime_type") or "").strip().lower()
            if not mime_type.startswith("image/") and not uri.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg")
            ):
                continue
            source_mode = str(item.get("source_mode") or producer_mode).strip().lower()
            if source_mode not in {"pptx_slides_to_images", "pptx_master_to_images"}:
                continue
            source_title = str(item.get("source_title") or "").strip() or None
            source_texts = [
                str(text).strip()
                for text in (item.get("source_texts") if isinstance(item.get("source_texts"), list) else [])
                if isinstance(text, str) and str(text).strip()
            ]
            source_layout_name = str(item.get("source_layout_name") or "").strip() or None
            source_layout_placeholders = [
                str(text).strip()
                for text in (
                    item.get("source_layout_placeholders")
                    if isinstance(item.get("source_layout_placeholders"), list)
                    else []
                )
                if isinstance(text, str) and str(text).strip()
            ]
            source_master_name = str(item.get("source_master_name") or "").strip() or None
            source_master_texts = [
                str(text).strip()
                for text in (item.get("source_master_texts") if isinstance(item.get("source_master_texts"), list) else [])
                if isinstance(text, str) and str(text).strip()
            ]
            artifact_id = str(dependency.get("artifact_id") or "artifact")
            producer_step_id = dependency.get("producer_step_id")
            digest = hashlib.sha1(f"{artifact_id}|{uri}".encode("utf-8")).hexdigest()[:16]
            source_label = "PPTX Master" if source_mode == "pptx_master_to_images" else "PPTX Slide"
            output.append(
                {
                    "asset_id": f"asset:pptx:{digest}",
                    "uri": uri,
                    "mime_type": mime_type or "image/png",
                    "is_image": True,
                    "source_type": "dependency_artifact",
                    "artifact_id": artifact_id,
                    "producer_step_id": producer_step_id if isinstance(producer_step_id, int) else None,
                    "producer_capability": "data_analyst",
                    "producer_mode": source_mode or producer_mode or "pptx_slides_to_images",
                    "source_mode": source_mode or producer_mode or "pptx_slides_to_images",
                    "label": "pptx_slide_reference",
                    "title": source_title or source_label,
                    "role_hints": [
                        "image",
                        "reference_image",
                        "layout_reference",
                        "template_source",
                        "pptx_slide_reference",
                    ],
                    "source_title": source_title,
                    "source_texts": source_texts,
                    "source_layout_name": source_layout_name,
                    "source_layout_placeholders": source_layout_placeholders,
                    "source_master_name": source_master_name,
                    "source_master_texts": source_master_texts,
                    "is_pptx_slide_reference": True,
                }
            )
            seen_by_uri.add(uri)

    return output


def _is_pptx_processing_asset(asset: dict[str, Any]) -> bool:
    if not isinstance(asset, dict):
        return False
    producer_mode = str(asset.get("producer_mode") or "").strip().lower()
    source_mode = str(asset.get("source_mode") or "").strip().lower()
    label = str(asset.get("label") or "").strip().lower()
    return (
        producer_mode in {"pptx_slides_to_images", "pptx_master_to_images"}
        or source_mode in {"pptx_slides_to_images", "pptx_master_to_images"}
        or label == "pptx_slide_reference"
    )


def _is_pptx_processing_dependency_artifact(item: dict[str, Any]) -> bool:
    if not isinstance(item, dict):
        return False
    producer_mode = str(item.get("producer_mode") or "").strip().lower()
    if producer_mode in {"pptx_slides_to_images", "pptx_master_to_images"}:
        return True

    content = item.get("content")
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except Exception:
            content = None
    if not isinstance(content, dict):
        return False

    output_value = content.get("output_value")
    if isinstance(output_value, dict):
        value_mode = str(output_value.get("mode") or "").strip().lower()
        if value_mode in {"pptx_slides_to_images", "pptx_master_to_images"}:
            return True

    output_files = content.get("output_files")
    if not isinstance(output_files, list):
        return False
    for row in output_files:
        if not isinstance(row, dict):
            continue
        source_mode = str(row.get("source_mode") or "").strip().lower()
        if source_mode in {"pptx_slides_to_images", "pptx_master_to_images"}:
            return True
    return False


def _order_assets_with_bindings(
    assets: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not assets or not bindings:
        return assets

    role_priority = [
        "layout_reference",
        "style_reference",
        "character_reference",
        "reference_image",
        "base_image",
        "mask_image",
    ]
    priority_index = {role: idx for idx, role in enumerate(role_priority)}
    by_id = {
        str(asset.get("asset_id")): asset
        for asset in assets
        if isinstance(asset, dict) and isinstance(asset.get("asset_id"), str)
    }
    ordered_ids: list[str] = []
    rows = sorted(
        [row for row in bindings if isinstance(row, dict) and isinstance(row.get("role"), str)],
        key=lambda row: priority_index.get(str(row.get("role")), 999),
    )
    for row in rows:
        asset_ids = row.get("asset_ids")
        if not isinstance(asset_ids, list):
            continue
        for asset_id in asset_ids:
            if not isinstance(asset_id, str):
                continue
            if asset_id in by_id and asset_id not in ordered_ids:
                ordered_ids.append(asset_id)

    ordered_assets = [by_id[asset_id] for asset_id in ordered_ids if asset_id in by_id]
    seen_ids = set(ordered_ids)
    for asset in assets:
        asset_id = asset.get("asset_id")
        if isinstance(asset_id, str) and asset_id in seen_ids:
            continue
        ordered_assets.append(asset)
    return ordered_assets


def _summarize_source_master_layout_meta(asset: dict[str, Any]) -> str | None:
    if not isinstance(asset, dict):
        return None
    placeholders = [
        str(item).strip().lower()
        for item in (
            asset.get("source_layout_placeholders")
            if isinstance(asset.get("source_layout_placeholders"), list)
            else []
        )
        if isinstance(item, str) and str(item).strip()
    ]
    placeholder_set = set(placeholders)
    body_count = sum(1 for item in placeholders if item == "body")
    has_title = bool({"title", "ctrtitle", "subtitle"} & placeholder_set)
    has_visual = bool({"pic", "obj", "media", "chart", "tbl"} & placeholder_set)

    if has_visual and (body_count >= 1 or has_title):
        return "コンテンツ＋絵"
    if body_count >= 2:
        return "2コンテンツ"
    if has_title and body_count >= 1:
        return "タイトル＋コンテンツ"
    if has_title:
        return "タイトル"
    if body_count >= 1:
        return "コンテンツ"

    layout_name = str(asset.get("source_layout_name") or "").strip()
    if layout_name:
        return layout_name
    return None


def _selector_asset_summary(
    *,
    mode: str,
    asset: dict[str, Any],
) -> dict[str, Any]:
    # Slide はスライドマスター選択に必要なメタ情報のみに絞る。
    if mode == "slide_render":
        return {
            "asset_id": asset.get("asset_id"),
            "is_pptx_slide_reference": bool(asset.get("is_pptx_slide_reference")),
            "source_master_layout_meta": _summarize_source_master_layout_meta(asset),
            "source_layout_name": str(asset.get("source_layout_name") or "").strip() or None,
            "source_layout_placeholders": (
                asset.get("source_layout_placeholders")
                if isinstance(asset.get("source_layout_placeholders"), list)
                else []
            ),
            "source_master_name": str(asset.get("source_master_name") or "").strip() or None,
            "source_master_texts": (
                asset.get("source_master_texts")
                if isinstance(asset.get("source_master_texts"), list)
                else []
            ),
        }
    return _asset_summary(asset)


def _infer_target_master_layout_meta(slide: dict[str, Any]) -> str:
    slide_number = slide.get("slide_number")
    if isinstance(slide_number, int) and slide_number == 1:
        return "タイトル"

    bullet_points = slide.get("bullet_points")
    bullet_count = len([item for item in bullet_points if isinstance(item, str) and item.strip()]) if isinstance(bullet_points, list) else 0
    title = str(slide.get("title") or "").strip()
    content_text = " ".join(
        str(value)
        for value in (
            slide.get("description"),
            slide.get("key_message"),
        )
        if isinstance(value, str) and value.strip()
    ).lower()
    has_visual_hint = any(token in content_text for token in ("図", "グラフ", "チャート", "画像", "写真", "icon", "chart", "diagram"))

    if has_visual_hint:
        return "コンテンツ＋絵"
    if title and bullet_count >= 1:
        return "タイトル＋コンテンツ"
    if bullet_count >= 2:
        return "2コンテンツ"
    return "コンテンツ"


def _selector_unit_summary(
    *,
    mode: str,
    slide: dict[str, Any],
) -> dict[str, Any] | None:
    slide_number = slide.get("slide_number")
    if not isinstance(slide_number, int):
        return None

    if mode == "slide_render":
        content_title = str(slide.get("title") or "").strip() or None
        text_candidates: list[str] = []
        for key in ("description", "key_message"):
            value = slide.get(key)
            if isinstance(value, str) and value.strip():
                text_candidates.append(value.strip())
        if isinstance(slide.get("bullet_points"), list):
            for item in slide.get("bullet_points"):
                if isinstance(item, str) and item.strip():
                    text_candidates.append(item.strip())

        seen_texts: set[str] = set()
        content_texts: list[str] = []
        for item in text_candidates:
            if item in seen_texts:
                continue
            seen_texts.add(item)
            content_texts.append(item)

        return {
            "slide_number": slide_number,
            "content_title": content_title,
            "content_texts": content_texts,
            "target_master_layout_meta": _infer_target_master_layout_meta(slide),
        }

    return {
        "slide_number": slide_number,
        "title": slide.get("title"),
        "description": slide.get("description"),
        "bullet_points": slide.get("bullet_points") if isinstance(slide.get("bullet_points"), list) else [],
    }


def _build_asset_router_selector_messages(
    *,
    mode: str,
    selector_input: dict[str, Any],
) -> list[Any]:
    prompt_state: dict[str, Any] = {
        "messages": [],
        "product_type": mode,
    }
    messages = apply_prompt_template("visualizer_asset_router", prompt_state)
    if not messages:
        messages = [SystemMessage(content="Visualizer asset router prompt is not available.")]
    messages.append(HumanMessage(content=json.dumps(selector_input, ensure_ascii=False), name="supervisor"))
    return messages


async def _plan_visual_asset_usage(
    *,
    llm: Any,
    mode: str,
    writer_slides: list[dict[str, Any]],
    selected_assets: list[dict[str, Any]],
    instruction: str | None,
    config: RunnableConfig,
) -> dict[int, list[str]]:
    image_assets = [asset for asset in selected_assets if _is_image_asset(asset)]
    if not writer_slides or not image_assets:
        return {}

    unit_briefs = []
    for slide in writer_slides:
        if not isinstance(slide, dict):
            continue
        unit_summary = _selector_unit_summary(mode=mode, slide=slide)
        if not isinstance(unit_summary, dict):
            continue
        unit_briefs.append(unit_summary)

    selector_input: dict[str, Any] = {
        "mode": mode,
        "units": unit_briefs,
        "candidate_assets": [
            _selector_asset_summary(mode=mode, asset=asset)
            for asset in image_assets
        ],
        "max_assets_per_unit": MAX_VISUAL_REFERENCES_PER_UNIT,
    }
    if mode != "slide_render":
        selector_input["instruction"] = instruction or ""

    selector_messages = _build_asset_router_selector_messages(
        mode=mode,
        selector_input=selector_input,
    )

    try:
        stream_config = config.copy()
        stream_config["run_name"] = "visualizer_asset_router"
        usage_plan = await run_structured_output(
            llm=llm,
            schema=VisualAssetUsagePlan,
            messages=selector_messages,
            config=stream_config,
            repair_hint="Schema: VisualAssetUsagePlan. No extra text.",
        )
    except Exception as e:
        logger.warning("Visualizer asset usage planning failed. Fallback to no assignment: %s", e)
        return {}

    valid_ids = {str(asset.get("asset_id")) for asset in image_assets if isinstance(asset.get("asset_id"), str)}
    image_assets_by_id = {
        str(asset.get("asset_id")): asset
        for asset in image_assets
        if isinstance(asset.get("asset_id"), str)
    }
    assignments: dict[int, list[str]] = {}
    for row in usage_plan.assignments:
        slide_number = row.slide_number
        if slide_number <= 0:
            continue
        deduped_ids: list[str] = []
        pptx_reference_count = 0
        for asset_id in row.asset_ids:
            if not isinstance(asset_id, str):
                continue
            if asset_id not in valid_ids or asset_id in deduped_ids:
                continue
            candidate = image_assets_by_id.get(asset_id)
            if (
                mode == "slide_render"
                and isinstance(candidate, dict)
                and _is_pptx_slide_reference_asset(candidate)
            ):
                if pptx_reference_count >= 1:
                    continue
                pptx_reference_count += 1
            deduped_ids.append(asset_id)
            if len(deduped_ids) >= MAX_VISUAL_REFERENCES_PER_UNIT:
                break
        assignments[slide_number] = deduped_ids

    return assignments


async def _resolve_asset_reference_inputs(
    assigned_assets: list[dict[str, Any]],
    cache: dict[str, bytes],
) -> tuple[list[str | bytes], list[str]]:
    reference_inputs: list[str | bytes] = []
    reference_uris: list[str] = []
    for asset in assigned_assets[:MAX_VISUAL_REFERENCES_PER_UNIT]:
        uri = str(asset.get("uri") or "").strip()
        if not uri:
            continue
        if uri in reference_uris:
            continue
        if uri.startswith("gs://"):
            reference_inputs.append(uri)
            reference_uris.append(uri)
            continue
        payload = cache.get(uri)
        if payload is None:
            payload = await asyncio.to_thread(download_blob_as_bytes, uri)
            if payload is None:
                logger.warning("Failed to fetch reference asset: %s", uri)
                continue
            cache[uri] = payload
        reference_inputs.append(payload)
        reference_uris.append(uri)
    return reference_inputs, reference_uris


def _load_character_sheet_template_bytes() -> bytes | None:
    try:
        return CHARACTER_SHEET_TEMPLATE_PATH.read_bytes()
    except Exception as e:
        logger.warning(
            "Character sheet template could not be loaded: %s (path=%s)",
            e,
            CHARACTER_SHEET_TEMPLATE_PATH,
        )
        return None

def _collect_artifacts_by_suffix(
    artifacts: dict[str, Any],
    suffix: str,
) -> list[tuple[int, str, dict[str, Any]]]:
    """Collect parsed artifacts by suffix, sorted by step id ascending."""
    items: list[tuple[int, str, dict[str, Any]]] = []
    for key, raw in artifacts.items():
        if not key.endswith(suffix):
            continue
        match = re.search(r"step_(\d+)_", key)
        step_id = int(match.group(1)) if match else -1
        parsed = _safe_json_loads(raw)
        if isinstance(parsed, dict):
            items.append((step_id, key, parsed))
    return sorted(items, key=lambda x: x[0])


def _find_latest_story_framework(artifacts: dict[str, Any]) -> dict[str, Any] | None:
    """Find latest writer story framework artifact from state."""
    candidates = _collect_artifacts_by_suffix(artifacts, "_story")
    for _, _, data in reversed(candidates):
        payload = data.get("story_framework")
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("concept"), str)
            and isinstance(payload.get("format_policy"), dict)
        ):
            return data
        if "logline" in data and "world_setting" in data and isinstance(data.get("key_beats"), list):
            return data
    return None


def _extract_story_framework_payload(writer_data: dict[str, Any]) -> dict[str, Any]:
    payload = writer_data.get("story_framework")
    if isinstance(payload, dict):
        return payload
    return {}


def _find_latest_character_sheet(artifacts: dict[str, Any]) -> dict[str, Any] | None:
    """Find latest writer character sheet artifact from state."""
    candidates = _collect_artifacts_by_suffix(artifacts, "_story")
    for _, _, data in reversed(candidates):
        if isinstance(data.get("characters"), list):
            return data
    return None


def _is_character_sheet_prompt_payload(prompt_payload: dict[str, Any]) -> bool:
    for key in ("compiled_prompt", "image_generation_prompt", "prompt_text"):
        value = prompt_payload.get(key)
        if isinstance(value, str) and CHARACTER_PROMPT_HEADER_PATTERN.search(value):
            return True
    return False


def _extract_image_url_from_visual_row(row: dict[str, Any]) -> str | None:
    candidate = row.get("generated_image_url")
    if isinstance(candidate, str) and candidate.strip():
        return candidate.strip()
    fallback = row.get("image_url")
    if isinstance(fallback, str) and fallback.strip():
        return fallback.strip()
    return None


def _extract_visual_output_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return rows

    prompts = payload.get("prompts")
    if isinstance(prompts, list):
        for item in prompts:
            if isinstance(item, dict):
                rows.append(dict(item))

    slides = payload.get("slides")
    if isinstance(slides, list):
        for item in slides:
            if not isinstance(item, dict):
                continue
            slide_number = item.get("slide_number")
            if isinstance(slide_number, int):
                row = dict(item)
                row["slide_number"] = slide_number
                rows.append(row)

    for page_key in ("design_pages", "comic_pages", "pages"):
        pages = payload.get(page_key)
        if not isinstance(pages, list):
            continue
        for item in pages:
            if not isinstance(item, dict):
                continue
            page_number = item.get("page_number")
            if not isinstance(page_number, int):
                continue
            row = dict(item)
            row["slide_number"] = page_number
            rows.append(row)

    characters = payload.get("characters")
    if isinstance(characters, list):
        for item in characters:
            if not isinstance(item, dict):
                continue
            character_number = item.get("character_number")
            if not isinstance(character_number, int):
                continue
            row = dict(item)
            row["slide_number"] = character_number
            rows.append(row)

    return rows


def _extract_generated_image_urls(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    urls: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _extract_image_url_from_visual_row(row)
        if not isinstance(url, str):
            continue
        if url not in urls:
            urls.append(url)
    return urls


def _find_latest_character_sheet_render_urls(artifacts: dict[str, Any]) -> list[str]:
    candidates = _collect_artifacts_by_suffix(artifacts, "_visual")
    for _, _, data in reversed(candidates):
        rows = _extract_visual_output_rows(data)
        if not rows:
            continue
        mode = str(data.get("mode") or "").strip().lower()
        is_character_mode = mode == "character_sheet_render" or isinstance(data.get("characters"), list)
        if not is_character_mode and not any(
            isinstance(row, dict) and _is_character_sheet_prompt_payload(row)
            for row in rows
        ):
            continue
        urls = _extract_generated_image_urls(rows)
        if urls:
            return urls
    return []


def _default_visualizer_mode(product_type: str | None) -> str:
    if product_type == "comic":
        return "comic_page_render"
    if product_type == "design":
        return "document_layout_render"
    return "slide_render"


def _normalize_visualizer_mode(mode: str) -> str:
    if mode == "infographic_render":
        logger.info("Visualizer mode 'infographic_render' is deprecated. Fallback to 'slide_render'.")
        return "slide_render"
    return mode


def _resolve_aspect_ratio(mode: str, step: dict[str, Any], state_ratio: str | None = None) -> str:
    if state_ratio:
        return state_ratio
        
    instruction_fields: list[str] = []
    for key in ("instruction", "description", "design_direction"):
        value = step.get(key)
        if isinstance(value, str):
            instruction_fields.append(value)
    merged = " ".join(instruction_fields)
    lowered = merged.lower()
    for ratio, hints in ASPECT_RATIO_HINTS.items():
        if any(h in merged or h in lowered for h in hints):
            return ratio
    return ASPECT_RATIO_BY_MODE.get(mode, "16:9")


def _resolve_asset_unit_meta(
    *,
    mode: str,
    product_type: str | None,
    slide_number: int,
) -> tuple[str, str, int]:
    if mode == "comic_page_render" or mode == "document_layout_render" or product_type in {"comic", "design"}:
        unit_kind = "page"
    elif mode == "character_sheet_render":
        unit_kind = "image"
    else:
        unit_kind = "slide"
    return f"{unit_kind}:{slide_number}", unit_kind, slide_number


def _normalize_visual_product_type(product_type: str | None) -> str | None:
    if product_type in {"slide", "design", "comic"}:
        return product_type
    return None


def _prompt_item_to_output_payload(
    prompt_item: ImagePrompt,
    *,
    title: str | None,
    selected_inputs: list[str] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": title,
        "layout_type": prompt_item.layout_type,
        "selected_inputs": selected_inputs or [],
        "rationale": prompt_item.rationale,
        "compiled_prompt": prompt_item.compiled_prompt,
        "generated_image_url": prompt_item.generated_image_url,
        "status": "completed"
        if isinstance(prompt_item.generated_image_url, str) and prompt_item.generated_image_url.strip()
        else "failed",
    }
    if isinstance(prompt_item.image_generation_prompt, str) and prompt_item.image_generation_prompt.strip():
        payload["image_generation_prompt"] = prompt_item.image_generation_prompt.strip()
    if prompt_item.structured_prompt is not None:
        payload["structured_prompt"] = prompt_item.structured_prompt.model_dump(exclude_none=True)
    if prompt_item.thought_signature is not None:
        payload["thought_signature"] = prompt_item.thought_signature.model_dump()
    return payload


def _build_visualizer_output(
    *,
    execution_summary: str,
    product_type: str | None,
    mode: str,
    prompts: list[ImagePrompt],
    generation_config: GenerationConfig,
    unit_meta_by_slide: dict[int, dict[str, Any]],
) -> VisualizerOutput:
    normalized_product_type = _normalize_visual_product_type(product_type)
    slides: list[dict[str, Any]] = []
    design_pages: list[dict[str, Any]] = []
    comic_pages: list[dict[str, Any]] = []
    characters: list[dict[str, Any]] = []

    for prompt_item in sorted(prompts, key=lambda item: item.slide_number):
        slide_number = int(prompt_item.slide_number)
        unit_meta = unit_meta_by_slide.get(slide_number, {})
        title = unit_meta.get("title") if isinstance(unit_meta.get("title"), str) else None
        selected_inputs = (
            unit_meta.get("selected_inputs")
            if isinstance(unit_meta.get("selected_inputs"), list)
            else []
        )
        base_payload = _prompt_item_to_output_payload(
            prompt_item,
            title=title,
            selected_inputs=[str(item) for item in selected_inputs if isinstance(item, str)],
        )

        if normalized_product_type == "slide":
            slides.append({"slide_number": slide_number, **base_payload})
            continue

        if normalized_product_type == "design":
            design_pages.append({"page_number": slide_number, **base_payload})
            continue

        if normalized_product_type == "comic":
            if mode == "character_sheet_render":
                character_name = (
                    unit_meta.get("character_name")
                    if isinstance(unit_meta.get("character_name"), str)
                    else None
                )
                characters.append(
                    {
                        "character_number": slide_number,
                        "character_name": character_name,
                        **base_payload,
                    }
                )
            else:
                comic_pages.append({"page_number": slide_number, **base_payload})
            continue

        slides.append({"slide_number": slide_number, **base_payload})

    return VisualizerOutput(
        execution_summary=execution_summary,
        product_type=normalized_product_type,
        mode=None if normalized_product_type == "design" else mode,
        slides=slides or None,
        design_pages=design_pages or None,
        comic_pages=comic_pages or None,
        characters=characters or None,
        generation_config=generation_config,
    )


def _writer_output_to_slides(writer_data: dict, mode: str) -> list[dict]:
    if not isinstance(writer_data, dict):
        return []

    if mode == "slide_render" and isinstance(writer_data.get("slides"), list):
        return writer_data.get("slides", [])

    if mode == "document_layout_render" and isinstance(writer_data.get("slides"), list):
        return writer_data.get("slides", [])

    if mode == "slide_render" and isinstance(writer_data.get("blocks"), list):
        slides: list[dict] = []
        title = writer_data.get("title", "Infographic")
        for idx, block in enumerate(writer_data.get("blocks", []), start=1):
            if not isinstance(block, dict):
                continue
            points = block.get("data_points") if isinstance(block.get("data_points"), list) else []
            slides.append(
                {
                    "slide_number": idx,
                    "title": f"{title}: {block.get('heading', f'Block {idx}')}",
                    "description": block.get("body", ""),
                    "bullet_points": [str(p) for p in points][:5],
                    "key_message": block.get("visual_hint"),
                }
            )
        return slides

    if mode == "character_sheet_render" and isinstance(writer_data.get("characters"), list):
        slides = []
        for idx, chara in enumerate(writer_data.get("characters", []), start=1):
            if not isinstance(chara, dict):
                continue
            details: list[str] = []
            for label, key in (
                ("Age", "age"),
                ("Gender", "gender"),
                ("Height", "height"),
                ("BodyProportion", "body_proportion"),
                ("Personality", "personality"),
                ("FaceLock", "face_features_lock"),
                ("HairLock", "hairstyle_lock"),
                ("BodyLock", "body_lock"),
            ):
                value = chara.get(key)
                if isinstance(value, str) and value.strip():
                    details.append(f"{label}: {value.strip()}")

            outfit_variants = chara.get("outfit_variants")
            if isinstance(outfit_variants, list) and outfit_variants:
                details.append(
                    "OutfitVariants: " + ", ".join(str(v).strip() for v in outfit_variants if str(v).strip())
                )

            color_palette = chara.get("color_palette")
            if isinstance(color_palette, dict):
                color_bits = []
                for key in ("main", "sub", "accent"):
                    value = color_palette.get(key)
                    if isinstance(value, str) and value.strip():
                        color_bits.append(f"{key}:{value.strip()}")
                if color_bits:
                    details.append("Palette: " + ", ".join(color_bits))

            forbidden_drift = chara.get("forbidden_drift")
            if isinstance(forbidden_drift, list) and forbidden_drift:
                details.append(
                    "Forbidden: " + ", ".join(str(v).strip() for v in forbidden_drift[:4] if str(v).strip())
                )

            slides.append(
                {
                    "slide_number": idx,
                    "title": f"Character Sheet: {chara.get('name', f'Character {idx}')}",
                    "description": chara.get("face_hair_anchors") or chara.get("appearance_core") or chara.get("appearance", ""),
                    "bullet_points": [
                        f"Role: {chara.get('story_role', chara.get('role', ''))}",
                        f"Personality: {chara.get('core_personality', chara.get('personality', ''))}",
                        f"Motivation: {chara.get('motivation', '')}",
                        f"Weakness/Fear: {chara.get('weakness_or_fear', '')}",
                        f"Silhouette: {chara.get('silhouette_signature', '')}",
                        *details[:6],
                    ],
                    "key_message": chara.get("silhouette_signature")
                    or ", ".join(chara.get("visual_keywords", [])[:5]) if isinstance(chara.get("visual_keywords"), list) else None,
                    "character_profile": chara,
                }
            )
        return slides

    if mode == "comic_page_render" and isinstance(writer_data.get("pages"), list):
        slides = []
        for page in writer_data.get("pages", []):
            if not isinstance(page, dict):
                continue
            page_number = int(page.get("page_number", len(slides) + 1))
            panels = page.get("panels") if isinstance(page.get("panels"), list) else []
            panel_descriptions = []
            for p in panels:
                if isinstance(p, dict):
                    panel_number = p.get("panel_number")
                    if isinstance(p.get("scene_description"), str) and str(p.get("scene_description")).strip():
                        summary = str(p.get("scene_description")).strip()
                    else:
                        detail_parts = []
                        for label, key in (
                            ("前景", "foreground"),
                            ("背景", "background"),
                            ("構図", "composition"),
                            ("カメラ", "camera"),
                            ("照明", "lighting"),
                        ):
                            value = p.get(key)
                            if isinstance(value, str) and value.strip() and value.strip() != "未指定":
                                detail_parts.append(f"{label}: {value.strip()}")
                        summary = " / ".join(detail_parts) if detail_parts else "詳細未指定"
                    prefix = f"P{panel_number}" if isinstance(panel_number, int) else "P?"
                    panel_descriptions.append(f"{prefix}: {summary}")
            page_description = page.get("page_goal")
            if not (isinstance(page_description, str) and page_description.strip()):
                page_description = panel_descriptions[0] if panel_descriptions else ""
            slides.append(
                {
                    "slide_number": page_number,
                    "title": f"Comic Page {page_number}",
                    "description": page_description,
                    "bullet_points": panel_descriptions[:5],
                    "key_message": page_description,
                }
            )
        return slides

    if mode == "document_layout_render" and isinstance(writer_data.get("pages"), list):
        slides = []
        for page in writer_data.get("pages", []):
            if not isinstance(page, dict):
                continue
            sections = page.get("sections") if isinstance(page.get("sections"), list) else []
            section_titles = [str(sec.get("heading", "")) for sec in sections if isinstance(sec, dict)]
            page_number = int(page.get("page_number", len(slides) + 1))
            slides.append(
                {
                    "slide_number": page_number,
                    "title": page.get("page_title", f"Page {page_number}"),
                    "description": page.get("purpose", ""),
                    "bullet_points": section_titles[:5],
                    "key_message": page.get("purpose"),
                }
            )
        return slides

    if mode == "story_framework_render":
        payload = _extract_story_framework_payload(writer_data)
        if payload:
            world_policy = payload.get("world_policy")
            era = world_policy.get("era") if isinstance(world_policy, dict) else None
            locations = world_policy.get("primary_locations") if isinstance(world_policy, dict) else []
            location_text = ""
            if isinstance(locations, list):
                joined = ", ".join(str(item) for item in locations[:3] if isinstance(item, str) and item.strip())
                location_text = joined
            description = " / ".join(item for item in [era, location_text] if isinstance(item, str) and item.strip())
            arc_overview = payload.get("arc_overview")
            bullet_points: list[str] = []
            if isinstance(arc_overview, list):
                for item in arc_overview:
                    if isinstance(item, dict):
                        phase = str(item.get("phase") or "").strip()
                        purpose = str(item.get("purpose") or "").strip()
                        if phase or purpose:
                            bullet_points.append(f"{phase}: {purpose}".strip(": "))
            return [
                {
                    "slide_number": 1,
                    "title": payload.get("concept", "Story Framework"),
                    "description": description,
                    "bullet_points": bullet_points[:6],
                    "key_message": payload.get("theme"),
                }
            ]
        return [
            {
                "slide_number": 1,
                "title": writer_data.get("logline", "Story Framework"),
                "description": writer_data.get("world_setting", ""),
                "bullet_points": writer_data.get("narrative_arc", []) if isinstance(writer_data.get("narrative_arc"), list) else [],
                "key_message": writer_data.get("tone_and_temperature"),
            }
        ]

    return []


def _text_or_default(value: Any, default: str = "未指定") -> str:
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return default


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _find_comic_page_payload(writer_data: dict[str, Any], page_number: int) -> dict[str, Any] | None:
    pages = writer_data.get("pages")
    if not isinstance(pages, list):
        return None
    for page in pages:
        if not isinstance(page, dict):
            continue
        raw_number = page.get("page_number")
        if isinstance(raw_number, int) and raw_number == page_number:
            return page
    if 1 <= page_number <= len(pages) and isinstance(pages[page_number - 1], dict):
        return pages[page_number - 1]
    return None


def _find_character_payload(
    writer_data: dict[str, Any],
    index: int,
    fallback_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    characters = writer_data.get("characters")
    if isinstance(characters, list) and 1 <= index <= len(characters):
        candidate = characters[index - 1]
        if isinstance(candidate, dict):
            return candidate
    if isinstance(fallback_profile, dict):
        return fallback_profile
    return None


def _build_comic_page_prompt_text(
    *,
    slide_number: int,
    slide_content: dict[str, Any],
    writer_data: dict[str, Any],
    character_sheet_data: dict[str, Any] | None = None,
    assigned_assets: list[dict[str, Any]] | None = None,
) -> str:
    page = _find_comic_page_payload(writer_data, slide_number)
    lines: list[str] = [
        f"#Page{slide_number}",
        "Mode: comic_page_render",
        "",
    ]

    page_goal = ""
    panels: list[dict[str, Any]] = []
    if isinstance(page, dict):
        page_goal = _text_or_default(page.get("page_goal"), "")
        raw_panels = page.get("panels")
        if isinstance(raw_panels, list):
            panels = [item for item in raw_panels if isinstance(item, dict)]

    if not page_goal:
        page_goal = _text_or_default(slide_content.get("description"), "未指定")
    lines.extend(["[Page Goal]", page_goal])

    character_rows = (
        character_sheet_data.get("characters")
        if isinstance(character_sheet_data, dict)
        else None
    )
    if isinstance(character_rows, list) and character_rows:
        lines.extend(["", "[Character Sheet Anchors]"])
        for idx, item in enumerate(character_rows[:8], start=1):
            if not isinstance(item, dict):
                continue
            name = _text_or_default(item.get("name"), f"Character {idx}")
            role = _text_or_default(item.get("story_role") or item.get("role"), "未指定")
            lines.append(f"- {name} ({role})")
            lines.append(f"  - Face/Hair anchors: {_text_or_default(item.get('face_hair_anchors'))}")
            lines.append(f"  - Costume anchors: {_text_or_default(item.get('costume_anchors'))}")
            lines.append(f"  - Silhouette signature: {_text_or_default(item.get('silhouette_signature'))}")

            palette = item.get("color_palette")
            if isinstance(palette, dict):
                palette_items = [
                    f"{key}={value.strip()}"
                    for key in ("main", "sub", "accent")
                    if isinstance((value := palette.get(key)), str) and value.strip()
                ]
                if palette_items:
                    lines.append("  - Color palette: " + ", ".join(palette_items))

            signature_items = _string_list(item.get("signature_items"))
            if signature_items:
                lines.append("  - Signature items: " + ", ".join(signature_items[:6]))

            forbidden_drift = _string_list(item.get("forbidden_drift"))
            if forbidden_drift:
                lines.append("  - Forbidden drift: " + ", ".join(forbidden_drift[:6]))

    lines.extend(["", "[Panels]"])

    if not panels:
        for bullet in _string_list(slide_content.get("bullet_points"))[:5]:
            lines.append(f"- {bullet}")
        if len(lines) == 7:
            lines.append("- 未指定")
        if assigned_assets:
            lines.extend(["", "[Reference Assets]"])
            for asset in assigned_assets:
                uri = str(asset.get("uri") or "").strip()
                if not uri:
                    continue
                label = str(asset.get("title") or asset.get("label") or "").strip()
                lines.append(f"- {uri}" + (f" ({label})" if label else ""))
        return "\n".join(lines)

    for idx, panel in enumerate(panels, start=1):
        panel_number = panel.get("panel_number")
        panel_label = panel_number if isinstance(panel_number, int) and panel_number > 0 else idx
        lines.append(f"Panel {panel_label}")
        lines.append(f"- Foreground: {_text_or_default(panel.get('foreground'))}")
        lines.append(f"- Background: {_text_or_default(panel.get('background'))}")
        lines.append(f"- Composition: {_text_or_default(panel.get('composition'))}")
        lines.append(f"- Camera: {_text_or_default(panel.get('camera'))}")
        lines.append(f"- Lighting: {_text_or_default(panel.get('lighting'))}")
        dialogue = _string_list(panel.get("dialogue"))
        if dialogue:
            lines.append("- Dialogue:")
            for line in dialogue:
                lines.append(f"  - {line}")
        negative_constraints = _string_list(panel.get("negative_constraints"))
        if negative_constraints:
            lines.append("- Negative constraints:")
            for item in negative_constraints:
                lines.append(f"  - {item}")
        lines.append("")

    if assigned_assets:
        lines.extend(["[Reference Assets]"])
        for asset in assigned_assets:
            uri = str(asset.get("uri") or "").strip()
            if not uri:
                continue
            label = str(asset.get("title") or asset.get("label") or "").strip()
            lines.append(f"- {uri}" + (f" ({label})" if label else ""))

    return "\n".join(lines).rstrip()


def _build_character_sheet_prompt_text(
    *,
    slide_number: int,
    slide_content: dict[str, Any],
    writer_data: dict[str, Any],
    story_framework_data: dict[str, Any],
    layout_template_enabled: bool,
    assigned_assets: list[dict[str, Any]] | None = None,
) -> str:
    character_profile = _find_character_payload(
        writer_data,
        slide_number,
        slide_content.get("character_profile") if isinstance(slide_content, dict) else None,
    ) or {}

    story_payload = (
        story_framework_data.get("story_framework")
        if isinstance(story_framework_data.get("story_framework"), dict)
        else story_framework_data
    )
    art_style = story_payload.get("art_style_policy") if isinstance(story_payload, dict) else {}

    lines: list[str] = [
        f"#Character{slide_number}",
        "Mode: character_sheet_render",
        "",
        "[Character]",
        f"- Name: {_text_or_default(character_profile.get('name'))}",
        f"- Role: {_text_or_default(character_profile.get('story_role') or character_profile.get('role'))}",
        f"- Core personality: {_text_or_default(character_profile.get('core_personality') or character_profile.get('personality'))}",
        f"- Motivation: {_text_or_default(character_profile.get('motivation'))}",
        f"- Weakness or fear: {_text_or_default(character_profile.get('weakness_or_fear'))}",
        f"- Speech style: {_text_or_default(character_profile.get('speech_style'), '指定なし')}",
        f"- Silhouette signature: {_text_or_default(character_profile.get('silhouette_signature'))}",
        f"- Face and hair anchors: {_text_or_default(character_profile.get('face_hair_anchors'))}",
        f"- Costume anchors: {_text_or_default(character_profile.get('costume_anchors'))}",
    ]

    color_palette = character_profile.get("color_palette")
    if isinstance(color_palette, dict):
        palette_items = [
            f"{key}={value.strip()}"
            for key in ("main", "sub", "accent")
            if isinstance((value := color_palette.get(key)), str) and value.strip()
        ]
        if palette_items:
            lines.append("- Color palette: " + ", ".join(palette_items))

    signature_items = _string_list(character_profile.get("signature_items"))
    if signature_items:
        lines.append("- Signature items:")
        for item in signature_items:
            lines.append(f"  - {item}")

    forbidden_drift = _string_list(character_profile.get("forbidden_drift"))
    if forbidden_drift:
        lines.append("- Forbidden drift:")
        for item in forbidden_drift:
            lines.append(f"  - {item}")

    lines.extend(
        [
            "",
            "[Style]",
            f"- Line style: {_text_or_default(art_style.get('line_style'), '指定なし') if isinstance(art_style, dict) else '指定なし'}",
            f"- Shading style: {_text_or_default(art_style.get('shading_style'), '指定なし') if isinstance(art_style, dict) else '指定なし'}",
        ]
    )

    style_negatives = (
        _string_list(art_style.get("negative_constraints"))
        if isinstance(art_style, dict)
        else []
    )
    if style_negatives:
        lines.append("- Global negative constraints:")
        for item in style_negatives:
            lines.append(f"  - {item}")

    if layout_template_enabled:
        lines.extend(["", "[Layout Template]", "- Provided reference template must be followed as-is."])

    if assigned_assets:
        lines.extend(["", "[Reference Assets]"])
        for asset in assigned_assets:
            uri = str(asset.get("uri") or "").strip()
            if not uri:
                continue
            label = str(asset.get("title") or asset.get("label") or "").strip()
            lines.append(f"- {uri}" + (f" ({label})" if label else ""))

    return "\n".join(lines).rstrip()


def _build_mechanical_comic_prompt_item(
    *,
    mode: str,
    slide_number: int,
    slide_content: dict[str, Any],
    writer_data: dict[str, Any],
    story_framework_data: dict[str, Any],
    character_sheet_data: dict[str, Any] | None = None,
    layout_template_enabled: bool,
    assigned_assets: list[dict[str, Any]] | None = None,
) -> ImagePrompt:
    if mode == "character_sheet_render":
        prompt_text = _build_character_sheet_prompt_text(
            slide_number=slide_number,
            slide_content=slide_content,
            writer_data=writer_data,
            story_framework_data=story_framework_data,
            layout_template_enabled=layout_template_enabled,
            assigned_assets=assigned_assets,
        )
    else:
        prompt_text = _build_comic_page_prompt_text(
            slide_number=slide_number,
            slide_content=slide_content,
            writer_data=writer_data,
            character_sheet_data=character_sheet_data,
            assigned_assets=assigned_assets,
        )

    return ImagePrompt(
        slide_number=slide_number,
        layout_type="other",
        structured_prompt=None,
        image_generation_prompt=prompt_text,
        rationale="Writer出力を機械的に整形したプロンプトを使用。",
    )


def _sanitize_filename(title: str) -> str:
    # Remove filesystem-unfriendly chars, keep unicode
    safe = re.sub(r"[\\\\/:*?\"<>|]", "_", title).strip()
    safe = re.sub(r"\s+", " ", safe)
    return safe or "Untitled"

async def _get_thread_title(thread_id: str | None, owner_uid: str | None) -> str | None:
    if not thread_id or not owner_uid:
        return None
    try:
        from src.core.workflow.service import _manager
        if not _manager.pool:
            return None
        async with _manager.pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT title FROM threads WHERE thread_id = %s AND owner_uid = %s",
                    (thread_id, owner_uid),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return row[0]
    except Exception as e:
        logger.warning(f"Failed to fetch thread title: {e}")
    return None

def compile_structured_prompt(
    structured: StructuredImagePrompt,
    slide_number: int = 1,
    mode: str = "slide_render",
    suppress_visual_style: bool = False,
) -> str:
    """
    構造化プロンプトをMarkdownスライド形式の最終プロンプトに変換。
    """
    prompt_lines = []
    
    normalized_mode = _normalize_visualizer_mode(mode)
    if normalized_mode == "comic_page_render":
        header = f"#Page{slide_number}"
    elif normalized_mode == "document_layout_render":
        header = f"# Page {slide_number} : {structured.main_title}"
    elif normalized_mode == "character_sheet_render":
        header = f"#Character{slide_number}"
    else:
        header = f"# Slide {slide_number} : {structured.main_title}"
    prompt_lines.append(header)

    if normalized_mode in {"slide_render", "document_layout_render"}:
        # Slide/design mode: subtitle is optional second-level heading.
        if structured.sub_title:
            prompt_lines.append(f"## {structured.sub_title}")
    else:
        # Non-slide modes keep the legacy title/subtitle heading layout.
        prompt_lines.append(f"## {structured.main_title}")
        if structured.sub_title:
            prompt_lines.append(f"### {structured.sub_title}")
    
    # Empty line before contents
    prompt_lines.append("")
    
    # Contents (optional)
    if structured.contents:
        prompt_lines.append(structured.contents)
        prompt_lines.append("")
    
    # Visual style
    if not suppress_visual_style:
        prompt_lines.append(f"Visual style: {structured.visual_style}")

    # text_policy / negative_constraints are retired for slide/design.
    is_slide_or_design_mode = normalized_mode in {"slide_render", "document_layout_render"}
    if not is_slide_or_design_mode:
        text_policy = structured.text_policy or "render_all_text"
        prompt_lines.append(f"Text policy: {text_policy}")
        if text_policy == "render_title_only":
            prompt_lines.append("Render title/subtitle only. Keep body text out of image.")
        elif text_policy == "no_text":
            prompt_lines.append("Do not render text in the image.")

        negatives = [
            str(item).strip()
            for item in (structured.negative_constraints or [])
            if str(item).strip()
        ]
        if negatives:
            prompt_lines.append("Negative constraints: " + ", ".join(negatives))
    
    # 最終プロンプト生成
    final_prompt = "\n".join(prompt_lines)
    logger.debug(f"Compiled visual prompt ({len(final_prompt)} chars)")
    
    return final_prompt


def _build_document_plaintext_prompt(
    structured: StructuredImagePrompt,
    *,
    slide_number: int,
) -> str:
    """Build a plain-text prompt for document layout rendering."""
    lines: list[str] = [
        f"Design a single editorial document page (page {slide_number}).",
        "Keep a clear information hierarchy, strong readability, and balanced white space.",
    ]
    if structured.main_title:
        lines.append(f"Main title: {structured.main_title}")
    if structured.sub_title:
        lines.append(f"Subtitle: {structured.sub_title}")
    if structured.contents:
        lines.append("Body content to render in-image:")
        lines.append(str(structured.contents))
    if structured.visual_style:
        lines.append(f"Visual style: {structured.visual_style}")
    return "\n".join(lines).strip()


def _resolve_image_generation_prompt(
    prompt_item: ImagePrompt,
    *,
    mode: str,
    suppress_visual_style: bool = False,
) -> str:
    """Resolve final image-generation prompt text per mode."""
    plain_prompt = (prompt_item.image_generation_prompt or "").strip()
    if prompt_item.structured_prompt is not None:
        if mode == "document_layout_render":
            return _build_document_plaintext_prompt(
                prompt_item.structured_prompt,
                slide_number=prompt_item.slide_number,
            )
        return compile_structured_prompt(
            prompt_item.structured_prompt,
            slide_number=prompt_item.slide_number,
            mode=mode,
            suppress_visual_style=suppress_visual_style,
        )
    if plain_prompt:
        return plain_prompt
    raise ValueError(
        f"Slide {prompt_item.slide_number} has neither structured_prompt nor image_generation_prompt"
    )


# Helper for single slide processing
async def process_single_slide(
    prompt_item: ImagePrompt, 
    override_reference_bytes: bytes | None = None,
    override_reference_url: str | None = None,
    additional_references: list[str | bytes] | None = None,
    has_template_references: bool = False,
    seed_override: int | None = None,
    session_id: str | None = None,
    aspect_ratio: str | None = None,
    mode: str = "slide_render",
) -> tuple[ImagePrompt, bytes | None, str | None]:
    """
    Helper function to process a single slide: generation or edit.
    """

    try:
        layout_type = getattr(prompt_item, 'layout_type', 'title_and_content')
        logger.info(f"Processing slide {prompt_item.slide_number} (layout: {layout_type})...")
        precompiled_prompt = (prompt_item.compiled_prompt or "").strip()
        if precompiled_prompt:
            final_prompt = precompiled_prompt
            logger.info(
                "Using precompiled generation prompt for slide %s (mode=%s)",
                prompt_item.slide_number,
                mode,
            )
        else:
            final_prompt = _resolve_image_generation_prompt(
                prompt_item,
                mode=mode,
                suppress_visual_style=has_template_references,
            )
            logger.info(
                "Resolved generation prompt (fallback) for slide %s (mode=%s)",
                prompt_item.slide_number,
                mode,
            )

        # === Reference Image Selection ===
        seed = None
        reference_image_bytes = None
        reference_url = None
        reference_inputs: list[str | bytes] = []
        
        # 1. Use Override (Anchor Image) if provided - highest priority
        if override_reference_bytes:
            logger.info(f"Using explicit override reference for slide {prompt_item.slide_number}")
            reference_image_bytes = override_reference_bytes
            reference_url = override_reference_url

        if reference_url and isinstance(reference_url, str) and reference_url.startswith("gs://"):
            reference_inputs.append(reference_url)
        elif reference_image_bytes:
            reference_inputs.append(reference_image_bytes)

        for ref in additional_references or []:
            if isinstance(ref, str):
                if ref and ref not in reference_inputs:
                    reference_inputs.append(ref)
            elif isinstance(ref, (bytes, bytearray)):
                reference_inputs.append(bytes(ref))

        if not precompiled_prompt:
            final_prompt = _append_reference_guidance(
                final_prompt,
                has_references=bool(reference_inputs),
                has_template_references=has_template_references,
            )
        prompt_item.compiled_prompt = final_prompt
        
        if seed_override is not None:
            seed = seed_override
        if seed is None:
            seed = random.randint(0, 2**31 - 1)

        logger.info(
            "Generating image %s with Seed: %s, RefCount: %s...",
            prompt_item.slide_number,
            seed,
            len(reference_inputs),
        )
        
        # 1. Generate Image (Blocking -> Thread)
        generation_result = await asyncio.to_thread(
            generate_image,
            final_prompt,
            seed=seed,
            reference_image=reference_inputs if reference_inputs else None,
            thought_signature=None,
            aspect_ratio=aspect_ratio
        )
        
        image_bytes, new_api_token = generation_result
        
        # 2. Upload to GCS (Blocking -> Thread)
        logger.info(f"Uploading image {prompt_item.slide_number} to GCS...")
        public_url = await asyncio.to_thread(
            upload_to_gcs, 
            image_bytes, 
            content_type="image/png",
            session_id=session_id,
            slide_number=prompt_item.slide_number
        )
        
        # 3. Update Result & Signature
        prompt_item.generated_image_url = public_url
        
        # Create ThoughtSignature
        prompt_item.thought_signature = ThoughtSignature(
            seed=seed,
            base_prompt=final_prompt,
            refined_prompt=None,
            model_version=AGENT_LLM_MAP["visualizer"],
            reference_image_url=reference_url or (prompt_item.thought_signature.reference_image_url if prompt_item.thought_signature else None),
            api_thought_signature=new_api_token
        )
        
        logger.info(f"Image generated and stored at: {public_url}")

        return prompt_item, image_bytes, None

    except Exception as image_error:
        logger.error(f"Failed to generate/upload image for prompt {prompt_item.slide_number}: {image_error}")
        return prompt_item, None, str(image_error)


async def process_slide_with_chat(
    prompt_item: ImagePrompt,
    chat_session,
    session_id: str | None = None,
    mode: str = "slide_render",
) -> ImagePrompt:
    """
    Helper function to process a single slide using a chat session for context carryover.
    """
    try:
        layout_type = getattr(prompt_item, 'layout_type', 'title_and_content')
        logger.info(f"[Chat] Processing slide {prompt_item.slide_number} (layout: {layout_type})...")
        precompiled_prompt = (prompt_item.compiled_prompt or "").strip()
        if precompiled_prompt:
            final_prompt = precompiled_prompt
            logger.info(
                "[Chat] Using precompiled generation prompt for slide %s (mode=%s)",
                prompt_item.slide_number,
                mode,
            )
        else:
            final_prompt = _resolve_image_generation_prompt(prompt_item, mode=mode)
            logger.info(
                "[Chat] Resolved generation prompt (fallback) for slide %s (mode=%s)",
                prompt_item.slide_number,
                mode,
            )
        
        logger.info(f"[Chat] Generating image {prompt_item.slide_number} via chat session...")
        
        # 1. Generate Image via Async Chat Session
        image_bytes = await send_message_for_image_async(
            chat_session,
            final_prompt,
            reference_image=None
        )
        
        # 2. Upload to GCS (Blocking -> Thread)
        logger.info(f"[Chat] Uploading image {prompt_item.slide_number} to GCS...")
        public_url = await asyncio.to_thread(
            upload_to_gcs, 
            image_bytes, 
            content_type="image/png",
            session_id=session_id,
            slide_number=prompt_item.slide_number
        )
        
        # 3. Update Result
        prompt_item.generated_image_url = public_url
        
        prompt_item.thought_signature = ThoughtSignature(
            seed=0,
            base_prompt=final_prompt,
            refined_prompt=None,
            model_version=AGENT_LLM_MAP["visualizer"],
            reference_image_url=None,
            api_thought_signature=None
        )
        
        logger.info(f"[Chat] Image generated and stored at: {public_url}")

        return prompt_item
        
    except Exception as image_error:
        logger.error(f"[Chat] Failed to generate/upload image for prompt {prompt_item.slide_number}: {image_error}")
        return prompt_item


async def visualizer_node(state: State, config: RunnableConfig) -> Command[Literal["supervisor"]]:
    """
    Node for the Visualizer agent. Responsible for generating slide images.
    """
    logger.info("Visualizer starting task")
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step.get("status") == "in_progress"
            and step.get("capability") == "visualizer"
        )
    except StopIteration:
        logger.error("Visualizer called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    mode = _normalize_visualizer_mode(
        str(current_step.get("mode") or _default_visualizer_mode(state.get("product_type")))
    )
    state_product_type = _normalize_visual_product_type(
        state.get("product_type") if isinstance(state.get("product_type"), str) else None
    )
    aspect_ratio = _resolve_aspect_ratio(mode, current_step, state.get("aspect_ratio"))
    artifacts = state.get("artifacts", {}) or {}
    selected_asset_bindings = resolve_asset_bindings_for_step(state, current_step.get("id"))
    selected_step_assets = _order_assets_with_bindings(
        resolve_selected_assets_for_step(state, current_step.get("id")),
        selected_asset_bindings,
    )
    if mode != "slide_render":
        selected_step_assets = [
            asset
            for asset in selected_step_assets
            if not _is_pptx_processing_asset(asset)
        ]
    selected_image_inputs = state.get("selected_image_inputs") or []
    attachments = [
        item
        for item in (state.get("attachments") or [])
        if isinstance(item, dict) and str(item.get("kind") or "").lower() != "pptx"
    ]
    design_dir = current_step.get("design_direction")
    dependency_context = resolve_step_dependency_context(state, current_step)
    if mode == "slide_render":
        pptx_slide_assets = _extract_pptx_slide_reference_assets(dependency_context)
        if pptx_slide_assets:
            seen_uris = {
                str(asset.get("uri") or "").strip()
                for asset in selected_step_assets
                if isinstance(asset, dict) and str(asset.get("uri") or "").strip()
            }
            merged_assets = list(selected_step_assets)
            for asset in pptx_slide_assets:
                uri = str(asset.get("uri") or "").strip()
                if not uri or uri in seen_uris:
                    continue
                seen_uris.add(uri)
                merged_assets.append(asset)
            selected_step_assets = _order_assets_with_bindings(
                merged_assets,
                selected_asset_bindings,
            )
            logger.info(
                "Visualizer merged %s pptx slide reference assets for slide mode.",
                len(pptx_slide_assets),
            )

    def _get_latest_artifact_by_suffix(suffix: str) -> dict | None:
        candidates: list[tuple[int, str]] = []
        for key in artifacts.keys():
            if key.endswith(suffix):
                match = re.search(r"step_(\d+)_", key)
                step_id = int(match.group(1)) if match else -1
                candidates.append((step_id, key))
        if not candidates:
            return None
        _, key = sorted(candidates, key=lambda x: x[0])[-1]
        return _safe_json_loads(artifacts.get(key))

    story_framework_data = _find_latest_story_framework(artifacts) or {}
    character_sheet_data = _find_latest_character_sheet(artifacts) or {}
    character_sheet_reference_urls = _find_latest_character_sheet_render_urls(artifacts)
    writer_data = _get_latest_artifact_by_suffix("_story") or {}
    if mode == "character_sheet_render" and character_sheet_data:
        writer_data = character_sheet_data

    if mode == "comic_page_render":
        characters = character_sheet_data.get("characters") if isinstance(character_sheet_data, dict) else None
        if not isinstance(characters, list) or len(characters) == 0:
            logger.error("comic_page_render requires writer character_sheet output but none was found.")
            result_summary = "Error: Character sheet is required for comic page rendering."
            state["plan"][step_index]["result_summary"] = result_summary
            content_json = build_worker_error_payload(
                error_text="Character sheet is required for comic page rendering.",
                failed_checks=["worker_execution", "missing_dependency"],
                notes="writer character_sheet artifact missing",
            )
            return create_worker_response(
                role="visualizer",
                content_json=content_json,
                result_summary=result_summary,
                current_step_id=current_step["id"],
                state=state,
                artifact_key_suffix="visual",
                artifact_title="Visual Assets",
                artifact_icon="AlertTriangle",
                artifact_preview_urls=[],
                is_error=True,
            )
        if not character_sheet_reference_urls:
            logger.error("comic_page_render requires character sheet rendered images but none were found.")
            result_summary = "Error: Character sheet rendered images are required for comic page rendering."
            state["plan"][step_index]["result_summary"] = result_summary
            content_json = build_worker_error_payload(
                error_text="Character sheet rendered images are required for comic page rendering.",
                failed_checks=["worker_execution", "missing_dependency"],
                notes="character_sheet_render visual artifact missing",
            )
            return create_worker_response(
                role="visualizer",
                content_json=content_json,
                result_summary=result_summary,
                current_step_id=current_step["id"],
                state=state,
                artifact_key_suffix="visual",
                artifact_title="Visual Assets",
                artifact_icon="AlertTriangle",
                artifact_preview_urls=[],
                is_error=True,
            )

    writer_slides = _writer_output_to_slides(writer_data, mode)
    data_analyst_data = _get_latest_artifact_by_suffix("_data")
    resolved_dependency_artifacts_for_prompt = dependency_context.get("resolved_dependency_artifacts", [])
    if mode != "slide_render":
        resolved_dependency_artifacts_for_prompt = [
            item
            for item in resolved_dependency_artifacts_for_prompt
            if not _is_pptx_processing_dependency_artifact(item)
        ]

    if not writer_slides:
        logger.error("Visualizer requires Writer output but none was found for mode=%s.", mode)
        result_summary = f"Error: Writer output not found for mode={mode}."
        state["plan"][step_index]["result_summary"] = result_summary
        content_json = build_worker_error_payload(
            error_text=f"Writer output not found for mode={mode}.",
            failed_checks=["worker_execution", "missing_dependency"],
            notes="writer artifact missing",
        )
        return create_worker_response(
            role="visualizer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step["id"],
            state=state,
            artifact_key_suffix="visual",
            artifact_title="Visual Assets",
            artifact_icon="AlertTriangle",
            artifact_preview_urls=[],
            is_error=True
        )

    # Plan context (LLM decides order/inputs)
    plan_context = {
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "instruction": current_step.get("instruction"),
        "planned_inputs": dependency_context["planned_inputs"],
        "depends_on_step_ids": dependency_context["depends_on_step_ids"],
        "resolved_dependency_artifacts": resolved_dependency_artifacts_for_prompt,
        "resolved_research_inputs": dependency_context["resolved_research_inputs"],
        "design_direction": design_dir,
        "selected_step_assets": [_asset_summary(asset) for asset in selected_step_assets[:20]],
        "selected_asset_bindings": selected_asset_bindings,
        "selected_image_inputs": selected_image_inputs,
        "attachments": attachments,
        "writer_output": writer_data,
        "writer_slides": writer_slides,
        "story_framework": story_framework_data if mode in {"character_sheet_render", "comic_page_render"} else None,
        "character_sheet": character_sheet_data if mode in {"character_sheet_render", "comic_page_render"} else None,
        "data_analyst": data_analyst_data if mode == "slide_render" else None,
        "layout_template_id": CHARACTER_SHEET_TEMPLATE_ID if mode == "character_sheet_render" else None,
    }
    character_sheet_template_bytes = (
        _load_character_sheet_template_bytes()
        if mode == "character_sheet_render"
        else None
    )
    if mode == "character_sheet_render" and character_sheet_template_bytes is None:
        logger.warning("character_sheet_render is running without local layout template reference.")

    llm = get_llm_by_type(AGENT_LLM_MAP["visualizer"])

    try:
        stream_config = config.copy()
        stream_config["run_name"] = "visualizer_plan"

        plan_messages = apply_prompt_template("visualizer_plan", state)
        plan_messages.append(
            HumanMessage(
                content=json.dumps(plan_context, ensure_ascii=False, indent=2),
                name="supervisor"
            )
        )

        visualizer_plan: VisualizerPlan = await run_structured_output(
            llm=llm,
            schema=VisualizerPlan,
            messages=plan_messages,
            config=stream_config,
            repair_hint="Schema: VisualizerPlan. No extra text."
        )

        logger.debug(f"Visualizer Plan: {visualizer_plan}")

        # Notify plan
        artifact_id = f"step_{current_step['id']}_visual"
        thread_id = config.get("configurable", {}).get("thread_id")
        user_uid = config.get("configurable", {}).get("user_uid")
        deck_title = await _get_thread_title(thread_id, user_uid) or "Untitled"
        await adispatch_custom_event(
            "data-visual-plan",
            {
                "artifact_id": artifact_id,
                "deck_title": deck_title,
                "plan": visualizer_plan.model_dump()
            },
            config=config
        )

        # Validate generation order
        outline_order = [s.get("slide_number") for s in writer_slides if "slide_number" in s]
        outline_order = [n for n in outline_order if isinstance(n, int)]
        generation_order = [n for n in visualizer_plan.generation_order if n in outline_order]
        for n in outline_order:
            if n not in generation_order:
                generation_order.append(n)

        plan_map = {s.slide_number: s for s in visualizer_plan.slides}
        selected_assets_by_id = {
            str(asset.get("asset_id")): asset
            for asset in selected_step_assets
            if isinstance(asset, dict) and isinstance(asset.get("asset_id"), str)
        }
        asset_usage_map = await _plan_visual_asset_usage(
            llm=llm,
            mode=mode,
            writer_slides=writer_slides,
            selected_assets=selected_step_assets,
            instruction=str(current_step.get("instruction") or ""),
            config=config,
        )

        updated_prompts: list[ImagePrompt] = []
        unit_meta_by_slide: dict[int, dict[str, Any]] = {}
        failed_image_errors: list[str] = []
        asset_unit_ledger = dict(state.get("asset_unit_ledger") or {})
        master_style: str | None = None
        reference_asset_cache: dict[str, bytes] = {}

        import uuid
        session_id = config.get("configurable", {}).get("thread_id") or str(uuid.uuid4())
        logger.info(f"Using session_id for GCS storage: {session_id}")

        for idx, slide_number in enumerate(generation_order, start=1):
            slide_content = next((s for s in writer_slides if s.get("slide_number") == slide_number), None)
            if not slide_content:
                logger.warning(f"Slide {slide_number} not found in story outline. Skipping.")
                continue

            plan_slide = plan_map.get(slide_number)
            use_local_character_sheet_template = (
                mode == "character_sheet_render" and character_sheet_template_bytes is not None
            )
            reference_policy = (
                "explicit"
                if use_local_character_sheet_template
                else (plan_slide.reference_policy if plan_slide else "none")
            )
            reference_url = (
                CHARACTER_SHEET_TEMPLATE_ID
                if use_local_character_sheet_template
                else (plan_slide.reference_url if plan_slide else None)
            )
            assigned_asset_ids = asset_usage_map.get(slide_number, [])
            assigned_assets = [
                selected_assets_by_id[asset_id]
                for asset_id in assigned_asset_ids
                if isinstance(asset_id, str) and asset_id in selected_assets_by_id
            ]
            if mode == "comic_page_render" and character_sheet_reference_urls:
                mandatory_assets = [
                    {
                        "asset_id": f"character_sheet_ref:{idx}",
                        "uri": uri,
                        "title": f"character_sheet_{idx}",
                        "label": "character_sheet_reference",
                        "source_type": "dependency_artifact",
                        "producer_mode": "character_sheet_render",
                        "is_image": True,
                    }
                    for idx, uri in enumerate(
                        character_sheet_reference_urls[:MAX_MANDATORY_CHARACTER_SHEET_REFERENCES],
                        start=1,
                    )
                    if isinstance(uri, str) and uri.strip()
                ]
            else:
                mandatory_assets = []

            mandatory_uris = {
                str(asset.get("uri")).strip()
                for asset in mandatory_assets
                if isinstance(asset, dict) and isinstance(asset.get("uri"), str) and str(asset.get("uri")).strip()
            }
            prioritized_assets = list(mandatory_assets)
            seen_uris = set(mandatory_uris)
            for asset in assigned_assets:
                if not isinstance(asset, dict):
                    continue
                uri = str(asset.get("uri") or "").strip()
                if not uri:
                    continue
                if uri in seen_uris:
                    continue
                seen_uris.add(uri)
                prioritized_assets.append(asset)
            assigned_assets = prioritized_assets
            has_template_references = (
                mode == "slide_render"
                and any(
                    isinstance(asset, dict) and _is_template_reference_asset(asset)
                    for asset in assigned_assets
                )
            )
            if mode == "slide_render":
                selected_template_refs = [
                    {
                        "asset_id": str(asset.get("asset_id") or ""),
                        "source_mode": (
                            str(asset.get("source_mode") or asset.get("producer_mode") or "").strip() or None
                        ),
                        "source_title": (
                            str(asset.get("source_title") or "").strip() or None
                        ),
                        "source_layout_name": (
                            str(asset.get("source_layout_name") or "").strip() or None
                        ),
                        "source_layout_placeholders": [
                            str(item).strip()
                            for item in (
                                asset.get("source_layout_placeholders")
                                if isinstance(asset.get("source_layout_placeholders"), list)
                                else []
                            )
                            if isinstance(item, str) and str(item).strip()
                        ],
                        "source_master_name": (
                            str(asset.get("source_master_name") or "").strip() or None
                        ),
                        "source_master_texts": [
                            str(item).strip()
                            for item in (
                                asset.get("source_master_texts")
                                if isinstance(asset.get("source_master_texts"), list)
                                else []
                            )
                            if isinstance(item, str) and str(item).strip()
                        ],
                        "uri": str(asset.get("uri") or "").strip(),
                    }
                    for asset in assigned_assets
                    if isinstance(asset, dict)
                    and _is_template_reference_asset(asset)
                    and isinstance(asset.get("uri"), str)
                    and str(asset.get("uri")).strip()
                ]
                if selected_template_refs:
                    logger.info(
                        "Slide %s selected template references: %s",
                        slide_number,
                        json.dumps(selected_template_refs, ensure_ascii=False),
                    )

            assigned_asset_summaries = [_asset_summary(asset) for asset in assigned_assets]
            selected_inputs_for_slide = [
                *(plan_slide.selected_inputs if plan_slide else []),
                *(
                    [f"SystemTemplate: {CHARACTER_SHEET_TEMPLATE_ID}"]
                    if use_local_character_sheet_template
                    else []
                ),
                *[
                    str(asset.get("uri"))
                    for asset in assigned_assets
                    if isinstance(asset, dict) and asset.get("uri")
                ],
                *[
                    str(item.get("image_url"))
                    for item in selected_image_inputs
                    if isinstance(item, dict) and item.get("image_url")
                ],
            ]
            selected_inputs_for_slide = [
                item.strip()
                for item in selected_inputs_for_slide
                if isinstance(item, str) and item.strip()
            ]

            unit_meta: dict[str, Any] = {
                "title": slide_content.get("title") if isinstance(slide_content.get("title"), str) else None,
                "selected_inputs": selected_inputs_for_slide,
            }
            if mode == "character_sheet_render":
                character_payload = _find_character_payload(
                    writer_data,
                    slide_number,
                    fallback_profile=(
                        slide_content.get("character_profile")
                        if isinstance(slide_content.get("character_profile"), dict)
                        else None
                    ),
                )
                if isinstance(character_payload, dict):
                    character_name = character_payload.get("name")
                    if isinstance(character_name, str) and character_name.strip():
                        unit_meta["character_name"] = character_name.strip()
            unit_meta_by_slide[slide_number] = unit_meta

            if mode in {"comic_page_render", "character_sheet_render"}:
                prompt_item = _build_mechanical_comic_prompt_item(
                    mode=mode,
                    slide_number=slide_number,
                    slide_content=slide_content,
                    writer_data=writer_data,
                    story_framework_data=story_framework_data,
                    character_sheet_data=character_sheet_data if mode == "comic_page_render" else None,
                    layout_template_enabled=use_local_character_sheet_template,
                    assigned_assets=assigned_assets,
                )
            else:
                prompt_context = {
                    "slide_number": slide_number,
                    "mode": mode,
                    "planned_inputs": dependency_context["planned_inputs"],
                    "depends_on_step_ids": dependency_context["depends_on_step_ids"],
                    "resolved_dependency_artifacts": resolved_dependency_artifacts_for_prompt,
                    "resolved_research_inputs": dependency_context["resolved_research_inputs"],
                    "writer_slide": slide_content,
                    "character_profile": slide_content.get("character_profile") if isinstance(slide_content, dict) else None,
                    "design_direction": design_dir,
                    "story_framework": story_framework_data if mode in {"character_sheet_render", "comic_page_render"} else None,
                    "character_sheet": character_sheet_data if mode in {"character_sheet_render", "comic_page_render"} else None,
                    "data_analyst": data_analyst_data if mode == "slide_render" else None,
                    "attachments": attachments,
                    "selected_step_assets": [_asset_summary(asset) for asset in selected_step_assets[:20]],
                    "selected_asset_bindings": selected_asset_bindings,
                    "assigned_asset_ids": assigned_asset_ids,
                    "assigned_assets": assigned_asset_summaries,
                    "selected_inputs": selected_inputs_for_slide,
                    "reference_policy": reference_policy,
                    "reference_url": reference_url,
                    "layout_template_id": CHARACTER_SHEET_TEMPLATE_ID if use_local_character_sheet_template else None,
                    "generation_notes": plan_slide.generation_notes if plan_slide else None,
                    "master_style": master_style,
                }

                prompt_state = {
                    "messages": [],
                    "product_type": state.get("product_type"),
                }
                prompt_messages = apply_prompt_template("visualizer_prompt", prompt_state)
                prompt_messages.append(
                    HumanMessage(
                        content=json.dumps(prompt_context, ensure_ascii=False, indent=2),
                        name="supervisor"
                    )
                )

                prompt_stream_config = config.copy()
                prompt_stream_config["run_name"] = "visualizer_prompt"

                prompt_item = await run_structured_output(
                    llm=llm,
                    schema=ImagePrompt,
                    messages=prompt_messages,
                    config=prompt_stream_config,
                    repair_hint="Schema: ImagePrompt. No extra text."
                )

            # Enforce slide number and layout if provided by planner
            prompt_item.slide_number = slide_number
            if mode == "character_sheet_render":
                prompt_item.layout_type = "other"
            elif plan_slide and plan_slide.layout_type:
                prompt_item.layout_type = plan_slide.layout_type  # override if planner prefers

            image_generation_prompt_text = prompt_item.image_generation_prompt
            logger.info(
                "Visualizer prompt item resolved: slide=%s mode=%s structured_prompt_present=%s image_generation_prompt_len=%s image_generation_prompt=%s",
                slide_number,
                mode,
                prompt_item.structured_prompt is not None,
                len(image_generation_prompt_text) if isinstance(image_generation_prompt_text, str) else 0,
                _log_prompt_preview(image_generation_prompt_text),
            )

            # Compile prompt for UI and generation (single source of truth)
            compiled_prompt = _resolve_image_generation_prompt(
                prompt_item,
                mode=mode,
                suppress_visual_style=has_template_references,
            )
            prompt_item.compiled_prompt = compiled_prompt

            # Update master style if needed
            if prompt_item.structured_prompt and not master_style:
                master_style = prompt_item.structured_prompt.visual_style

            # Resolve unit meta early (used by prompt/image events and ledger).
            asset_unit_id, asset_unit_kind, asset_unit_index = _resolve_asset_unit_meta(
                mode=mode,
                product_type=state_product_type,
                slide_number=slide_number,
            )

            # Reference image policy
            reference_bytes = None
            reference_url = None
            if use_local_character_sheet_template:
                reference_url = CHARACTER_SHEET_TEMPLATE_ID
                reference_bytes = character_sheet_template_bytes
            elif plan_slide and plan_slide.reference_policy == "explicit" and plan_slide.reference_url:
                reference_url = plan_slide.reference_url
                if not reference_url.startswith("gs://"):
                    reference_bytes = await asyncio.to_thread(download_blob_as_bytes, reference_url)
            elif plan_slide and plan_slide.reference_policy == "previous":
                logger.info(
                    "Skipping deprecated reference_policy=previous for slide %s.",
                    slide_number,
                )

            additional_references, assigned_reference_uris = await _resolve_asset_reference_inputs(
                assigned_assets,
                reference_asset_cache,
            )
            if assigned_reference_uris:
                logger.info(
                    "Slide %s uses %s selected reference assets.",
                    slide_number,
                    len(assigned_reference_uris),
                )

            prompt_for_event = _append_reference_guidance(
                compiled_prompt,
                has_references=bool(reference_bytes or reference_url or additional_references),
                has_template_references=has_template_references,
            )
            prompt_item.compiled_prompt = prompt_for_event

            prompt_event_data: dict[str, Any] = {
                "artifact_id": artifact_id,
                "asset_unit_id": asset_unit_id,
                "asset_unit_kind": asset_unit_kind,
                "deck_title": deck_title,
                "slide_number": slide_number,
                "title": slide_content.get("title"),
                "layout_type": prompt_item.layout_type,
                "prompt_text": prompt_for_event,
                "structured_prompt": (
                    prompt_item.structured_prompt.model_dump(exclude_none=True)
                    if prompt_item.structured_prompt
                    else None
                ),
                "rationale": prompt_item.rationale,
                "selected_inputs": selected_inputs_for_slide,
            }
            if state_product_type != "design":
                prompt_event_data["mode"] = mode
            await adispatch_custom_event(
                "data-visual-prompt",
                prompt_event_data,
                config=config
            )

            # Generate image
            processed, _image_bytes, image_error = await process_single_slide(
                prompt_item,
                override_reference_bytes=reference_bytes,
                override_reference_url=reference_url,
                additional_references=additional_references,
                has_template_references=has_template_references,
                session_id=session_id,
                aspect_ratio=aspect_ratio,
                mode=mode,
            )

            updated_prompts.append(processed)
            if image_error:
                failed_image_errors.append(f"slide={slide_number}: {image_error}")
            image_event_data: dict[str, Any] = {
                "artifact_id": artifact_id,
                "asset_unit_id": asset_unit_id,
                "asset_unit_kind": asset_unit_kind,
                "deck_title": deck_title,
                "slide_number": slide_number,
                "title": slide_content.get("title"),
                "image_url": processed.generated_image_url,
                "status": "completed" if processed.generated_image_url else "failed",
            }
            if state_product_type != "design":
                image_event_data["mode"] = mode
            await adispatch_custom_event(
                "data-visual-image",
                image_event_data,
                config=config
            )
            asset_unit_ledger[asset_unit_id] = {
                "unit_id": asset_unit_id,
                "unit_kind": asset_unit_kind,
                "unit_index": asset_unit_index,
                "artifact_id": artifact_id,
                "image_url": processed.generated_image_url,
                "producer_step_id": current_step.get("id"),
                "title": slide_content.get("title"),
            }

        updated_prompts.sort(key=lambda x: x.slide_number)
        total_count = len(updated_prompts)
        success_count = sum(1 for item in updated_prompts if isinstance(item.generated_image_url, str) and item.generated_image_url.strip())

        if total_count == 0 or success_count == 0:
            error_text = "All visual image generations failed."
            notes = "; ".join(failed_image_errors[:3]) if failed_image_errors else "no successful image URL returned"
            content_json = build_worker_error_payload(
                error_text=error_text,
                failed_checks=["worker_execution", "all_images_failed"],
                notes=notes,
            )
            result_summary = f"Error: {error_text}"
            state["plan"][step_index]["result_summary"] = result_summary

            return create_worker_response(
                role="visualizer",
                content_json=content_json,
                result_summary=result_summary,
                current_step_id=current_step["id"],
                state=state,
                artifact_key_suffix="visual",
                artifact_title="Visual Assets",
                artifact_icon="AlertTriangle",
                artifact_preview_urls=[],
                is_error=True,
                extra_update={"asset_unit_ledger": asset_unit_ledger},
            )

        execution_summary = visualizer_plan.execution_summary
        if success_count < total_count:
            execution_summary = f"{visualizer_plan.execution_summary}（生成 {success_count}/{total_count}）"

        # Build final Visualizer output
        generation_config = GenerationConfig(
            thinking_level="high",
            media_resolution="medium",
            aspect_ratio=aspect_ratio,
        )
        visualizer_output = _build_visualizer_output(
            execution_summary=execution_summary,
            product_type=state_product_type,
            mode=mode,
            prompts=updated_prompts,
            generation_config=generation_config,
            unit_meta_by_slide=unit_meta_by_slide,
        )

        content_json = json.dumps(visualizer_output.model_dump(exclude_none=True), ensure_ascii=False, indent=2)
        result_summary = visualizer_output.execution_summary

        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="visualizer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step["id"],
            state=state,
            artifact_key_suffix="visual",
            artifact_title="Visual Assets",
            artifact_icon="Image",
            artifact_preview_urls=[p.generated_image_url for p in updated_prompts if p.generated_image_url],
            extra_update={"asset_unit_ledger": asset_unit_ledger},
        )

    except Exception as e:
        logger.error(f"Visualizer failed: {e}")
        content_json = build_worker_error_payload(
            error_text=str(e),
            failed_checks=["worker_execution"],
        )
        result_summary = f"Error: {str(e)}"

        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="visualizer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step["id"],
            state=state,
            artifact_key_suffix="visual",
            artifact_title="Visual Assets",
            artifact_icon="AlertTriangle",
            artifact_preview_urls=[],
            is_error=True
        )
