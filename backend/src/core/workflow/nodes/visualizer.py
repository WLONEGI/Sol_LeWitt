import logging
import json
import random
import asyncio
import re
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
    StructuredImagePrompt,
    ThoughtSignature
)
from src.core.workflow.state import State

# Updated Imports for Services
from src.domain.designer.generator import generate_image, create_image_chat_session_async, send_message_for_image_async
from src.infrastructure.storage.gcs import upload_to_gcs, download_blob_as_bytes

from .common import create_worker_response, run_structured_output

logger = logging.getLogger(__name__)

def _safe_json_loads(value: Any) -> Any | None:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return None
    if isinstance(value, dict):
        return value
    return None

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
            logger.info(f"Using legacy prompt for slide {prompt_item.slide_number}")
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
            reference_image=reference_image_bytes,
            thought_signature=previous_thought_signature_token
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
            logger.info(f"[Chat] Using legacy prompt for slide {prompt_item.slide_number}")
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
            if step["status"] == "in_progress" and step["role"] == "visualizer"
        )
    except StopIteration:
        logger.error("Visualizer called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    artifacts = state.get("artifacts", {}) or {}
    design_dir = current_step.get("design_direction")

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

    story_data = _get_latest_artifact_by_suffix("_story") or {}
    story_slides = story_data.get("slides", [])
    data_analyst_data = _get_latest_artifact_by_suffix("_data")

    if not story_slides:
        logger.error("Visualizer requires Storywriter output but none was found.")
        result_summary = "Error: Storywriter output not found."
        state["plan"][step_index]["result_summary"] = result_summary
        return create_worker_response(
            role="visualizer",
            content_json=json.dumps({"error": "Storywriter output not found."}, ensure_ascii=False),
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
        "instruction": current_step.get("instruction"),
        "design_direction": design_dir,
        "storywriter_slides": story_slides,
        "data_analyst": data_analyst_data,
        "previous_generations": previous_generations or None
    }

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
        outline_order = [s.get("slide_number") for s in story_slides if "slide_number" in s]
        outline_order = [n for n in outline_order if isinstance(n, int)]
        generation_order = [n for n in visualizer_plan.generation_order if n in outline_order]
        for n in outline_order:
            if n not in generation_order:
                generation_order.append(n)

        plan_map = {s.slide_number: s for s in visualizer_plan.slides}

        updated_prompts: list[ImagePrompt] = []
        master_style: str | None = None
        last_generated_image_bytes: bytes | None = None
        last_generated_image_url: str | None = None

        import uuid
        session_id = config.get("configurable", {}).get("thread_id") or str(uuid.uuid4())
        logger.info(f"Using session_id for GCS storage: {session_id}")

        for idx, slide_number in enumerate(generation_order, start=1):
            slide_content = next((s for s in story_slides if s.get("slide_number") == slide_number), None)
            if not slide_content:
                logger.warning(f"Slide {slide_number} not found in story outline. Skipping.")
                continue

            plan_slide = plan_map.get(slide_number)
            prompt_context = {
                "slide_number": slide_number,
                "storywriter_slide": slide_content,
                "design_direction": design_dir,
                "data_analyst": data_analyst_data,
                "selected_inputs": plan_slide.selected_inputs if plan_slide else [],
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
            if plan_slide and plan_slide.layout_type:
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
            await adispatch_custom_event(
                "data-visual-prompt",
                {
                    "artifact_id": artifact_id,
                    "deck_title": deck_title,
                    "slide_number": slide_number,
                    "title": slide_content.get("title"),
                    "layout_type": prompt_item.layout_type,
                    "prompt_text": compiled_prompt,
                    "structured_prompt": prompt_item.structured_prompt.model_dump() if prompt_item.structured_prompt else None,
                    "rationale": prompt_item.rationale,
                    "selected_inputs": plan_slide.selected_inputs if plan_slide else []
                },
                config=config
            )

            # Reference image policy
            reference_bytes = None
            reference_url = None
            if plan_slide and plan_slide.reference_policy == "explicit" and plan_slide.reference_url:
                reference_url = plan_slide.reference_url
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
                            reference_bytes = await asyncio.to_thread(download_blob_as_bytes, reference_url)
                            break

            # Generate image
            processed, image_bytes = await process_single_slide(
                prompt_item,
                previous_generations=previous_generations,
                override_reference_bytes=reference_bytes,
                override_reference_url=reference_url,
                session_id=session_id
            )

            updated_prompts.append(processed)
            if image_bytes and processed.generated_image_url:
                last_generated_image_bytes = image_bytes
                last_generated_image_url = processed.generated_image_url
            await adispatch_custom_event(
                "data-visual-image",
                {
                    "artifact_id": artifact_id,
                    "deck_title": deck_title,
                    "slide_number": slide_number,
                    "title": slide_content.get("title"),
                    "image_url": processed.generated_image_url,
                    "status": "completed" if processed.generated_image_url else "failed"
                },
                config=config
            )

        updated_prompts.sort(key=lambda x: x.slide_number)

        # Build final Visualizer output
        visualizer_output = VisualizerOutput(
            execution_summary=visualizer_plan.execution_summary,
            prompts=updated_prompts
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
            artifact_preview_urls=[p.generated_image_url for p in updated_prompts if p.generated_image_url]
        )

    except Exception as e:
        logger.error(f"Visualizer failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
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
