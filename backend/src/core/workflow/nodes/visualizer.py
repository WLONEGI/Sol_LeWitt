import logging
import json
import random
import asyncio
import re
from pathlib import Path
from typing import Literal, Any

from langchain_core.messages import HumanMessage
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
    run_structured_output,
)

logger = logging.getLogger(__name__)

ASPECT_RATIO_BY_MODE = {
    "slide_render": "16:9",
    "infographic_render": "1:1",
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

def _safe_json_loads(value: Any) -> Any | None:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    if isinstance(value, dict):
        return value
    return None


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

    if mode in {"slide_render", "infographic_render"} and isinstance(writer_data.get("slides"), list):
        return writer_data.get("slides", [])

    if mode == "infographic_render" and isinstance(writer_data.get("blocks"), list):
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

            slides.append(
                {
                    "slide_number": idx,
                    "title": f"Character Sheet: {chara.get('name', f'Character {idx}')}",
                    "description": chara.get("appearance_core") or chara.get("appearance", ""),
                    "bullet_points": [
                        f"Role: {chara.get('role', '')}",
                        f"Personality: {chara.get('personality', '')}",
                        f"Motivation: {chara.get('motivation', '')}",
                        *details[:6],
                    ],
                    "key_message": ", ".join(chara.get("visual_keywords", [])[:5]) if isinstance(chara.get("visual_keywords"), list) else None,
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
                    panel_descriptions.append(str(p.get("scene_description", "")))
            slides.append(
                {
                    "slide_number": page_number,
                    "title": f"Comic Page {page_number}",
                    "description": page.get("page_goal", ""),
                    "bullet_points": panel_descriptions[:5],
                    "key_message": page.get("page_goal"),
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
    slide_number: int = 1
) -> str:
    """
    構造化プロンプトをMarkdownスライド形式の最終プロンプトに変換。
    """
    prompt_lines = []
    
    # Slide Header: # Slide1: Title Slide
    prompt_lines.append(f"# Slide{slide_number}: {structured.slide_type}")
    
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
    logger.debug(f"Compiled slide prompt ({len(final_prompt)} chars)")
    
    return final_prompt


# Helper for single slide processing
async def process_single_slide(
    prompt_item: ImagePrompt, 
    previous_generations: list[dict] | None = None, 
    override_reference_bytes: bytes | None = None,
    override_reference_url: str | None = None,
    seed_override: int | None = None,
    session_id: str | None = None,
    aspect_ratio: str | None = None,
) -> tuple[ImagePrompt, bytes | None]:
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
                slide_number=prompt_item.slide_number
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
        
        if seed_override is not None:
            seed = seed_override
        if seed is None:
            seed = random.randint(0, 2**31 - 1)

        logger.info(f"Generating image {prompt_item.slide_number} with Seed: {seed}, Ref: {bool(reference_image_bytes)}...")
        
        # 1. Generate Image (Blocking -> Thread)
        generation_result = await asyncio.to_thread(
            generate_image,
            final_prompt,
            seed=seed,
            reference_image=reference_url if reference_url and reference_url.startswith("gs://") else reference_image_bytes,
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

        return prompt_item, image_bytes

    except Exception as image_error:
        logger.error(f"Failed to generate/upload image for prompt {prompt_item.slide_number}: {image_error}")
        return prompt_item, None


async def process_slide_with_chat(
    prompt_item: ImagePrompt,
    chat_session,
    session_id: str | None = None,
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
                slide_number=prompt_item.slide_number
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

    mode = str(current_step.get("mode") or _default_visualizer_mode(state.get("product_type")))
    aspect_ratio = _resolve_aspect_ratio(mode, current_step, state.get("aspect_ratio"))
    artifacts = state.get("artifacts", {}) or {}
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

        updated_prompts: list[ImagePrompt] = []
        asset_unit_ledger = dict(state.get("asset_unit_ledger") or {})
        master_style: str | None = None
        last_generated_image_bytes: bytes | None = None
        last_generated_image_url: str | None = None

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
                "selected_inputs": [
                    *(plan_slide.selected_inputs if plan_slide else []),
                    *(
                        [f"SystemTemplate: {CHARACTER_SHEET_TEMPLATE_ID}"]
                        if use_local_character_sheet_template
                        else []
                    ),
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

            prompt_item: ImagePrompt = await run_structured_output(
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
                    slide_number=slide_number
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

            # Generate image
            processed, image_bytes = await process_single_slide(
                prompt_item,
                previous_generations=previous_generations,
                override_reference_bytes=reference_bytes,
                override_reference_url=reference_url,
                session_id=session_id,
                aspect_ratio=aspect_ratio
            )

            updated_prompts.append(processed)
            if image_bytes and processed.generated_image_url:
                last_generated_image_bytes = image_bytes
                last_generated_image_url = processed.generated_image_url
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

        # Build final Visualizer output
        visualizer_output = VisualizerOutput(
            execution_summary=visualizer_plan.execution_summary,
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
