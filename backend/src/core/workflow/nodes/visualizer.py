import logging
import json
import random
import asyncio
from typing import Literal, Any

from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from src.shared.config.settings import settings
from src.shared.config import AGENT_LLM_MAP
from src.infrastructure.llm.llm import get_llm_by_type
from src.resources.prompts.template import apply_prompt_template
from src.shared.schemas import (
    VisualizerOutput,
    ImagePrompt,
    StructuredImagePrompt,
    ThoughtSignature
)
from src.core.workflow.state import State

# Updated Imports for Services
from src.domain.designer.generator import generate_image, create_image_chat_session_async, send_message_for_image_async
from src.infrastructure.storage.gcs import upload_to_gcs, download_blob_as_bytes

from .common import create_worker_response

logger = logging.getLogger(__name__)

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
    session_id: str | None = None,
) -> ImagePrompt:
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
        
        # === Reference Image Selection ===
        seed = None
        reference_image_bytes = None
        reference_url = None
        previous_thought_signature_token = None
        
        # 1. Use Override (Anchor Image) if provided - highest priority
        if override_reference_bytes:
            logger.info(f"Using explicit override reference for slide {prompt_item.slide_number}")
            reference_image_bytes = override_reference_bytes
        
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

        return prompt_item

    except Exception as image_error:
        logger.error(f"Failed to generate/upload image for prompt {prompt_item.slide_number}: {image_error}")
        return prompt_item


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
    
    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"

    design_dir = current_step.get('design_direction')
    if design_dir:
        context += f"\n\n[Design Direction from Planner]:\n{design_dir}\n"

    previous_generations: list[dict] = []
    for key, json_str in state.get("artifacts", {}).items():
        if key.endswith("_visual"):
            try:
                data = json.loads(json_str)
                if "prompts" in data:
                    previous_generations.extend(data["prompts"])
            except Exception:
                pass
    
    if previous_generations:
        context += f"\n\n# PREVIOUS GENERATIONS (EDIT MODE)\nUser wants to modify these. Maintain consistency with seed/style if specified:\n{json.dumps(previous_generations, ensure_ascii=False, indent=2)}"
    
    messages = apply_prompt_template("visualizer", state)
    
    supervisor_content = [{"type": "text", "text": context}]

    messages.append(HumanMessage(content=supervisor_content, name="supervisor"))
    
    llm = get_llm_by_type(AGENT_LLM_MAP["visualizer"])
    
    try:
        # Use with_structured_output explicitly for Pydantic parsing reliability
        structured_llm = llm.with_structured_output(VisualizerOutput)
        visualizer_output: VisualizerOutput = await structured_llm.ainvoke(messages)
        
        logger.debug(f"Visualizer Output: {visualizer_output}")

        prompts = visualizer_output.prompts
        updated_prompts: list[ImagePrompt] = []
        
        import uuid
        # Use thread_id from config for GCS session_id to ensure persistence
        session_id = config.get("configurable", {}).get("thread_id") or str(uuid.uuid4())
        logger.info(f"Using session_id for GCS storage: {session_id}")

        # Use sequential chat-based generation (no template images)
        target_prompts = prompts
        if target_prompts:
            seed = random.randint(0, 2**31 - 1)
            chat_session = await create_image_chat_session_async(seed)
            logger.info(f"[Sequential] Starting sequential generation for {len(target_prompts)} slides with context carryover...")
            
            for idx, prompt_item in enumerate(target_prompts):
                logger.info(f"[Sequential] Processing slide {idx + 1}/{len(target_prompts)}...")
                processed = await process_slide_with_chat(
                    prompt_item,
                    chat_session,
                    session_id=session_id,
                )
                updated_prompts.append(processed)
        
        updated_prompts.sort(key=lambda x: x.slide_number)
        visualizer_output.prompts = updated_prompts
        
        content_json = json.dumps(visualizer_output.model_dump(), ensure_ascii=False, indent=2)
        logger.info(f"Visualizer generated {len(visualizer_output.prompts)} image prompts with artifacts")
        result_summary = visualizer_output.execution_summary

        # Update result summary in plan
        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="visualizer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step['id'],
            state=state,
            artifact_key_suffix="visual",
            artifact_title="Visual Assets",
            artifact_icon="Image",
            artifact_preview_urls=[p.generated_image_url for p in visualizer_output.prompts if p.generated_image_url]
        )

    except Exception as e:
        logger.error(f"Visualizer failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"
        
        # Update result summary in plan
        state["plan"][step_index]["result_summary"] = result_summary

        return create_worker_response(
            role="visualizer",
            content_json=content_json,
            result_summary=result_summary,
            current_step_id=current_step['id'],
            state=state,
            artifact_key_suffix="visual",
            artifact_title="Visual Assets",
            artifact_icon="AlertTriangle",
            artifact_preview_urls=[],
            is_error=True
        )
