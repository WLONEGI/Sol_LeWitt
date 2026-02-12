import logging
import json
import random
import asyncio
import re
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
MAX_VISUAL_REFERENCES_PER_UNIT = 3


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
    }


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
        slide_number = slide.get("slide_number")
        if not isinstance(slide_number, int):
            continue
        unit_briefs.append(
            {
                "slide_number": slide_number,
                "title": slide.get("title"),
                "description": slide.get("description"),
                "bullet_points": slide.get("bullet_points") if isinstance(slide.get("bullet_points"), list) else [],
            }
        )

    selector_input = {
        "mode": mode,
        "instruction": instruction or "",
        "units": unit_briefs,
        "candidate_assets": [_asset_summary(asset) for asset in image_assets],
        "max_assets_per_unit": MAX_VISUAL_REFERENCES_PER_UNIT,
    }

    selector_messages = [
        SystemMessage(
            content=(
                "あなたはVisualizerの参照画像ルータです。"
                "各unit(slide/page)に対して、候補asset_idから必要な画像のみを選択してください。"
                "出力はVisualAssetUsagePlanスキーマのJSONのみ。"
                "選択は最大3件/unit。不要なら空配列。"
            ),
        ),
        HumanMessage(content=json.dumps(selector_input, ensure_ascii=False), name="supervisor"),
    ]

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
    assignments: dict[int, list[str]] = {}
    for row in usage_plan.assignments:
        slide_number = row.slide_number
        if slide_number <= 0:
            continue
        deduped_ids: list[str] = []
        for asset_id in row.asset_ids:
            if not isinstance(asset_id, str):
                continue
            if asset_id not in valid_ids or asset_id in deduped_ids:
                continue
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


def _writer_output_to_slides(writer_data: dict, mode: str) -> list[dict]:
    if not isinstance(writer_data, dict):
        return []

    if mode == "slide_render" and isinstance(writer_data.get("slides"), list):
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
    aspect_ratio: str,
    assigned_assets: list[dict[str, Any]] | None = None,
) -> str:
    page = _find_comic_page_payload(writer_data, slide_number)
    lines: list[str] = [
        f"#Page{slide_number}",
        "Mode: comic_page_render",
        f"Aspect ratio: {aspect_ratio}",
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
    lines.extend(["[Page Goal]", page_goal, "", "[Panels]"])

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
    aspect_ratio: str,
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
        f"Aspect ratio: {aspect_ratio}",
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
    aspect_ratio: str,
    layout_template_enabled: bool,
    assigned_assets: list[dict[str, Any]] | None = None,
) -> ImagePrompt:
    if mode == "character_sheet_render":
        prompt_text = _build_character_sheet_prompt_text(
            slide_number=slide_number,
            slide_content=slide_content,
            writer_data=writer_data,
            story_framework_data=story_framework_data,
            aspect_ratio=aspect_ratio,
            layout_template_enabled=layout_template_enabled,
            assigned_assets=assigned_assets,
        )
    else:
        prompt_text = _build_comic_page_prompt_text(
            slide_number=slide_number,
            slide_content=slide_content,
            writer_data=writer_data,
            aspect_ratio=aspect_ratio,
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
) -> str:
    """
    構造化プロンプトをMarkdownスライド形式の最終プロンプトに変換。
    """
    prompt_lines = []
    
    normalized_mode = _normalize_visualizer_mode(mode)
    if normalized_mode in {"document_layout_render", "comic_page_render"}:
        header = f"#Page{slide_number}"
    elif normalized_mode == "character_sheet_render":
        header = f"#Character{slide_number}"
    else:
        header = f"#Slide{slide_number}"
    prompt_lines.append(header)
    # Main Title: ## The Evolution of Japan's Economy
    prompt_lines.append(f"## {structured.main_title}")
    
    # Sub Title (optional): ### From Post-War Recovery...
    if structured.sub_title:
        prompt_lines.append(f"### {structured.sub_title}")
    
    # Empty line before contents
    prompt_lines.append("")
    
    # Contents (optional)
    if structured.contents:
        prompt_lines.append(structured.contents)
        prompt_lines.append("")
    
    # Visual style
    prompt_lines.append(f"Visual style: {structured.visual_style}")

    # Text rendering policy
    prompt_lines.append(f"Text policy: {structured.text_policy}")
    if structured.text_policy == "render_all_text":
        prompt_lines.append(
            "Render all provided text (title, subtitle, and contents) in-image without omission."
        )
    elif structured.text_policy == "render_title_only":
        prompt_lines.append("Render title/subtitle only. Keep body text out of image.")
    else:
        prompt_lines.append("Do not render text in the image.")

    # Negative constraints
    if structured.negative_constraints:
        prompt_lines.append(
            "Negative constraints: " + ", ".join(
                str(item).strip() for item in structured.negative_constraints if str(item).strip()
            )
        )
    
    # 最終プロンプト生成
    final_prompt = "\n".join(prompt_lines)
    logger.debug(f"Compiled visual prompt ({len(final_prompt)} chars)")
    
    return final_prompt


# Helper for single slide processing
async def process_single_slide(
    prompt_item: ImagePrompt, 
    previous_generations: list[dict] | None = None, 
    override_reference_bytes: bytes | None = None,
    override_reference_url: str | None = None,
    additional_references: list[str | bytes] | None = None,
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
        
        # === Compile Structured Prompt (v2) ===
        if prompt_item.structured_prompt is not None:
            final_prompt = compile_structured_prompt(
                prompt_item.structured_prompt,
                slide_number=prompt_item.slide_number,
                mode=mode,
            )
            logger.info(f"Using structured prompt for slide {prompt_item.slide_number}")
        elif prompt_item.image_generation_prompt:
            final_prompt = prompt_item.image_generation_prompt
            logger.info(f"Using string prompt for slide {prompt_item.slide_number}")
        else:
            raise ValueError(f"Slide {prompt_item.slide_number} has neither structured_prompt nor image_generation_prompt")

        prompt_item.compiled_prompt = final_prompt

        # === Reference Image Selection ===
        seed = None
        reference_image_bytes = None
        reference_url = None
        previous_thought_signature_token = None
        reference_inputs: list[str | bytes] = []
        
        # 1. Use Override (Anchor Image) if provided - highest priority
        if override_reference_bytes:
            logger.info(f"Using explicit override reference for slide {prompt_item.slide_number}")
            reference_image_bytes = override_reference_bytes
            reference_url = override_reference_url
        
        # 2. Check for matching previous generation (Deep Edit)
        elif previous_generations:
            for prev in previous_generations:
                if prev.get("slide_number") != prompt_item.slide_number:
                    continue
                
                # Reuse Seed and Thought Signature
                prev_sig = prev.get("thought_signature")
                if prev_sig:
                    if "seed" in prev_sig:
                        seed = prev_sig["seed"]
                        logger.info(f"Reusing seed {seed} from ThoughtSignature")
                    
                    if "api_thought_signature" in prev_sig and prev_sig["api_thought_signature"]:
                        previous_thought_signature_token = prev_sig["api_thought_signature"]
                        logger.info("Found persistent 'api_thought_signature' for Deep Edit consistency.")

                # Reference Anchor (Visual Consistency)
                if prev.get("generated_image_url"):
                    reference_url = prev["generated_image_url"]
                    if reference_url.startswith("gs://"):
                        logger.info(f"Using GCS URI directly as reference anchor: {reference_url}")
                    else:
                        logger.info(f"Downloading reference anchor from {reference_url}...")
                        try:
                            reference_image_bytes = await asyncio.to_thread(download_blob_as_bytes, reference_url)
                        except Exception as e:
                            logger.warning(f"Failed to download previous reference image: {e}")
                
                break

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
            thought_signature=previous_thought_signature_token,
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
        
        # === Compile Structured Prompt (v2) ===
        if prompt_item.structured_prompt is not None:
            final_prompt = compile_structured_prompt(
                prompt_item.structured_prompt,
                slide_number=prompt_item.slide_number,
                mode=mode,
            )
            logger.info(f"[Chat] Using structured prompt for slide {prompt_item.slide_number}")
        elif prompt_item.image_generation_prompt:
            final_prompt = prompt_item.image_generation_prompt
            logger.info(f"[Chat] Using string prompt for slide {prompt_item.slide_number}")
        else:
            raise ValueError(f"Slide {prompt_item.slide_number} has neither structured_prompt nor image_generation_prompt")
        
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
    aspect_ratio = _resolve_aspect_ratio(mode, current_step, state.get("aspect_ratio"))
    artifacts = state.get("artifacts", {}) or {}
    selected_step_assets = resolve_selected_assets_for_step(state, current_step.get("id"))
    selected_image_inputs = state.get("selected_image_inputs") or []
    attachments = [
        item
        for item in (state.get("attachments") or [])
        if isinstance(item, dict) and str(item.get("kind") or "").lower() != "pptx"
    ]
    design_dir = current_step.get("design_direction")
    dependency_context = resolve_step_dependency_context(state, current_step)

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
    writer_data = _get_latest_artifact_by_suffix("_story") or {}
    if mode == "character_sheet_render" and character_sheet_data:
        writer_data = character_sheet_data
    writer_slides = _writer_output_to_slides(writer_data, mode)
    data_analyst_data = _get_latest_artifact_by_suffix("_data")

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

    previous_generations: list[dict] = []
    for key, json_str in artifacts.items():
        if key.endswith("_visual"):
            data = _safe_json_loads(json_str)
            if isinstance(data, dict) and "prompts" in data:
                previous_generations.extend(data["prompts"])

    # Plan context (LLM decides order/inputs)
    plan_context = {
        "mode": mode,
        "aspect_ratio": aspect_ratio,
        "instruction": current_step.get("instruction"),
        "planned_inputs": dependency_context["planned_inputs"],
        "depends_on_step_ids": dependency_context["depends_on_step_ids"],
        "resolved_dependency_artifacts": dependency_context["resolved_dependency_artifacts"],
        "resolved_research_inputs": dependency_context["resolved_research_inputs"],
        "design_direction": design_dir,
        "selected_step_assets": [_asset_summary(asset) for asset in selected_step_assets[:20]],
        "selected_image_inputs": selected_image_inputs,
        "attachments": attachments,
        "writer_output": writer_data,
        "writer_slides": writer_slides,
        "story_framework": story_framework_data if mode == "character_sheet_render" else None,
        "character_sheet": character_sheet_data if mode == "character_sheet_render" else None,
        "data_analyst": data_analyst_data,
        "previous_generations": previous_generations or None,
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
        failed_image_errors: list[str] = []
        asset_unit_ledger = dict(state.get("asset_unit_ledger") or {})
        master_style: str | None = None
        last_generated_image_bytes: bytes | None = None
        last_generated_image_url: str | None = None
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
            assigned_asset_summaries = [_asset_summary(asset) for asset in assigned_assets]
            if mode in {"comic_page_render", "character_sheet_render"}:
                prompt_item = _build_mechanical_comic_prompt_item(
                    mode=mode,
                    slide_number=slide_number,
                    slide_content=slide_content,
                    writer_data=writer_data,
                    story_framework_data=story_framework_data,
                    aspect_ratio=aspect_ratio,
                    layout_template_enabled=use_local_character_sheet_template,
                    assigned_assets=assigned_assets,
                )
            else:
                prompt_context = {
                    "slide_number": slide_number,
                    "mode": mode,
                    "planned_inputs": dependency_context["planned_inputs"],
                    "depends_on_step_ids": dependency_context["depends_on_step_ids"],
                    "resolved_dependency_artifacts": dependency_context["resolved_dependency_artifacts"],
                    "resolved_research_inputs": dependency_context["resolved_research_inputs"],
                    "writer_slide": slide_content,
                    "character_profile": slide_content.get("character_profile") if isinstance(slide_content, dict) else None,
                    "design_direction": design_dir,
                    "aspect_ratio": aspect_ratio,
                    "story_framework": story_framework_data if mode == "character_sheet_render" else None,
                    "character_sheet": character_sheet_data if mode == "character_sheet_render" else None,
                    "data_analyst": data_analyst_data,
                    "attachments": attachments,
                    "selected_step_assets": [_asset_summary(asset) for asset in selected_step_assets[:20]],
                    "assigned_asset_ids": assigned_asset_ids,
                    "assigned_assets": assigned_asset_summaries,
                    "selected_inputs": [
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
                    ],
                    "reference_policy": reference_policy,
                    "reference_url": reference_url,
                    "layout_template_id": CHARACTER_SHEET_TEMPLATE_ID if use_local_character_sheet_template else None,
                    "generation_notes": plan_slide.generation_notes if plan_slide else None,
                    "master_style": master_style,
                    "previous_generations": previous_generations or None
                }

                prompt_state = {"messages": []}
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

            # Compile prompt for UI
            if prompt_item.structured_prompt is not None:
                compiled_prompt = compile_structured_prompt(
                    prompt_item.structured_prompt,
                    slide_number=slide_number,
                    mode=mode,
                )
            else:
                compiled_prompt = prompt_item.image_generation_prompt or ""
            prompt_item.compiled_prompt = compiled_prompt

            # Update master style if needed
            if prompt_item.structured_prompt and not master_style:
                master_style = prompt_item.structured_prompt.visual_style

            # Emit prompt event
            asset_unit_id, asset_unit_kind, asset_unit_index = _resolve_asset_unit_meta(
                mode=mode,
                product_type=state.get("product_type"),
                slide_number=slide_number,
            )
            await adispatch_custom_event(
                "data-visual-prompt",
                {
                    "artifact_id": artifact_id,
                    "asset_unit_id": asset_unit_id,
                    "asset_unit_kind": asset_unit_kind,
                    "deck_title": deck_title,
                    "slide_number": slide_number,
                    "title": slide_content.get("title"),
                    "layout_type": prompt_item.layout_type,
                    "prompt_text": compiled_prompt,
                    "structured_prompt": prompt_item.structured_prompt.model_dump() if prompt_item.structured_prompt else None,
                    "rationale": prompt_item.rationale,
                    "selected_inputs": [
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
                },
                config=config
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
                if last_generated_image_bytes:
                    reference_bytes = last_generated_image_bytes
                    reference_url = last_generated_image_url
                else:
                    # fallback: previous generation of same slide (edit mode)
                    for prev in previous_generations:
                        if prev.get("slide_number") == slide_number and prev.get("generated_image_url"):
                            reference_url = prev["generated_image_url"]
                            if not reference_url.startswith("gs://"):
                                reference_bytes = await asyncio.to_thread(download_blob_as_bytes, reference_url)
                            break

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

            # Generate image
            processed, image_bytes, image_error = await process_single_slide(
                prompt_item,
                previous_generations=previous_generations,
                override_reference_bytes=reference_bytes,
                override_reference_url=reference_url,
                additional_references=additional_references,
                session_id=session_id,
                aspect_ratio=aspect_ratio,
                mode=mode,
            )

            updated_prompts.append(processed)
            if image_bytes and processed.generated_image_url:
                last_generated_image_bytes = image_bytes
                last_generated_image_url = processed.generated_image_url
            elif image_error:
                failed_image_errors.append(f"slide={slide_number}: {image_error}")
            await adispatch_custom_event(
                "data-visual-image",
                {
                    "artifact_id": artifact_id,
                    "asset_unit_id": asset_unit_id,
                    "asset_unit_kind": asset_unit_kind,
                    "deck_title": deck_title,
                    "slide_number": slide_number,
                    "title": slide_content.get("title"),
                    "image_url": processed.generated_image_url,
                    "status": "completed" if processed.generated_image_url else "failed"
                },
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
        visualizer_output = VisualizerOutput(
            execution_summary=execution_summary,
            prompts=updated_prompts,
            generation_config=GenerationConfig(
                thinking_level="high",
                media_resolution="high",
                aspect_ratio=aspect_ratio,
            )
        )

        content_json = json.dumps(visualizer_output.model_dump(), ensure_ascii=False, indent=2)
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
