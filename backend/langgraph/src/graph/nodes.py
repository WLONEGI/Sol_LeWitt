import asyncio
import logging
import json
import random
import base64
from copy import deepcopy
from typing import Literal, Any

from google.genai import types

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_core.callbacks.manager import adispatch_custom_event
from langgraph.types import Command, Send
from langgraph.graph import StateGraph, START, END

from src.agents import storywriter_agent, visualizer_agent
from src.agents.llm import get_llm_by_type
from src.config import TEAM_MEMBERS
from src.config.agents import AGENT_LLM_MAP
from src.config.settings import settings

from src.prompts.template import apply_prompt_template
from src.schemas import (
    PlannerOutput,
    StorywriterOutput,
    VisualizerOutput,
    DataAnalystOutput,
    ReviewOutput,
    ThoughtSignature,
    ImagePrompt,
    StructuredImagePrompt,
    ResearchTask,     # NEW
    ResearchResult,   # NEW
    ResearchTaskList, # NEW - for dynamic decomposition
)
from src.utils.image_generation import generate_image, create_image_chat_session_async, send_message_for_image_async
from src.utils.storage import upload_to_gcs, download_blob_as_bytes


from .graph_types import State, TaskStep, ResearchSubgraphState

logger = logging.getLogger(__name__)


def compile_structured_prompt(
    structured: StructuredImagePrompt,
    slide_number: int = 1
) -> str:
    """
    構造化プロンプトをMarkdownスライド形式の最終プロンプトに変換。
    
    出力形式:
    ```
    # Slide1: Title Slide
    ## The Evolution of Japan's Economy
    ### From Post-War Recovery to Future Innovation
    
    [Contents]
    
    Visual style: [English description]
    ```
    
    Args:
        structured: StructuredImagePrompt オブジェクト
        slide_number: スライド番号
        
    Returns:
        str: Geminiに送信する最終的なテキストプロンプト
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


def _update_artifact(state: State, key: str, value: Any) -> dict[str, Any]:
    """Helper to update artifacts dictionary."""
    artifacts = state.get("artifacts", {})
    artifacts[key] = value
    return artifacts


# Removed legacy research_node





def storywriter_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Node for the Storywriter agent.
    
    Generates slide content and proceeds to Supervisor.
    """
    logger.info("Storywriter starting task")
    # Find the current in-progress step for this agent
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "storywriter"
        )
    except StopIteration:
        logger.error("Storywriter called but no in_progress step found.")
        return Command(goto="supervisor", update={})
    
    # Provide context including artifacts
    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"
    
    # Build messages with prompt template
    messages = apply_prompt_template("storywriter", state)
    messages.append(HumanMessage(content=context, name="supervisor"))
    
    # Use with_structured_output for automatic parsing (Gemini Controlled Generation)
    llm = get_llm_by_type(AGENT_LLM_MAP["storywriter"])
    structured_llm = llm.with_structured_output(StorywriterOutput)
    
    try:
        # with_structured_output returns parsed Pydantic object directly
        result: StorywriterOutput = structured_llm.invoke(messages)
        content_json = result.model_dump_json(exclude_none=True)
        logger.info(f"✅ Storywriter generated {len(result.slides)} slides")
        
    except Exception as e:
        logger.error(f"Storywriter structured output failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"

    # Update result summary in plan
    # current_step is a reference to the dict in state["plan"], but we must ensure we save the plan back.
    current_step["result_summary"] = result.execution_summary if 'result' in locals() else result_summary

    # Create UI-specific messages
    # 1. Result Summary
    result_message = AIMessage(
        content=f"Storywriter generated {len(result.slides)} slides based on the plan.",
        additional_kwargs={
            "ui_type": "worker_result", 
            "role": "storywriter", 
            "status": "completed",
            "result_summary": result_summary
        }, 
        name="storywriter_ui"
    )
    
    # 2. Artifact Button
    artifact_message = AIMessage(
        content="Slides Generated",
        additional_kwargs={
            "ui_type": "artifact_view",
            "artifact_id": f"step_{current_step['id']}_story",
            "title": "Story Content",
            "icon": "FileText"
        },
        name="storywriter_artifact"
    )

    return Command(
        update={
            "messages": [
                HumanMessage(content=settings.RESPONSE_FORMAT.format(role="storywriter", content=content_json), name="storywriter"),
                result_message,
                artifact_message
            ],
            "artifacts": _update_artifact(state, f"step_{current_step['id']}_story", content_json),
            "plan": state["plan"]
        },
        goto="supervisor",
    )



# Helper for single slide processing
async def process_single_slide(
    prompt_item: ImagePrompt, 
    previous_generations: list[dict] | None = None, 
    override_reference_bytes: bytes | None = None,
    design_context: Any = None,  # DesignContext | None (型ヒントは循環参照を避けるためAny)
    session_id: str | None = None,  # セッションIDでGCSフォルダ分け
) -> ImagePrompt:
    """
    Helper function to process a single slide: generation or edit.

    Handles the core image generation logic, including:
    1. Template reference image selection (based on layout_type in design_context).
    2. Seed management for determinism (reusing seed from ThoughtSignature).
    3. Reference image handling for Deep Edit / Visual Consistency.
    4. **Structured Prompt Compilation**: Converts StructuredImagePrompt to final text.
    5. Image generation via Vertex AI.
    6. Uploading to GCS.

    Args:
        prompt_item (ImagePrompt): The prompt object containing the image generation instruction.
        previous_generations (list[dict] | None): List of previous generation data for "Deep Edit" logic.
        override_reference_bytes (bytes | None): Optional image bytes to force as a reference (e.g., Anchor Image).
                                                 If provided, this takes precedence over previous generations.
        design_context: DesignContext with layout-based template images (optional).

    Returns:
        ImagePrompt: Updated prompt item with `generated_image_url` and `thought_signature` populated.

    Raises:
        Exception: Captures and logs generation failures, returning the item with None URL to allow partial batch success.
    """

    try:
        layout_type = getattr(prompt_item, 'layout_type', 'title_and_content')
        logger.info(f"Processing slide {prompt_item.slide_number} (layout: {layout_type})...")
        
        # === Compile Structured Prompt (v2) ===
        # 優先度: structured_prompt > image_generation_prompt
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
        previous_thought_signature_token = None # [NEW] Unknown opaque token from Gemini 3.0 API
        
        # 1. Use Override (Anchor Image) if provided - highest priority
        if override_reference_bytes:
            logger.info(f"Using explicit override reference for slide {prompt_item.slide_number}")
            reference_image_bytes = override_reference_bytes
        
        # 2. [NEW] Use DesignContext layout-based template image
        elif design_context:
            # design_context.get_template_image_for_layout() returns bytes or None
            layout_ref = design_context.get_template_image_for_layout(layout_type)
            if layout_ref:
                reference_image_bytes = layout_ref
                logger.info(f"Using template image for layout '{layout_type}'")
            else:
                logger.warning(f"No template image found for layout '{layout_type}'")
        
        # 3. Check for matching previous generation (Deep Edit)
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
                    
                    # [NEW] Reuse opaque API token for Gemini 3.0 Consistency
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
        # Returns tuple (bytes, thought_signature_str)
        generation_result = await asyncio.to_thread(
            generate_image,
            final_prompt,  # CHANGED: Use compiled prompt
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
            base_prompt=final_prompt,  # CHANGED: Store compiled prompt
            refined_prompt=None,
            model_version=AGENT_LLM_MAP["visualizer"],
            reference_image_url=reference_url or (prompt_item.thought_signature.reference_image_url if prompt_item.thought_signature else None),
            api_thought_signature=new_api_token # [NEW] Store the opaque token
        )
        
        logger.info(f"Image generated and stored at: {public_url}")
        return prompt_item

    except Exception as image_error:
        logger.error(f"Failed to generate/upload image for prompt {prompt_item.slide_number}: {image_error}")
        # Return item as-is (with None URL) to avoid crashing the whole batch
        return prompt_item


# [NEW] チャットセッションを用いた画像生成（コンテキスト引き継ぎ対応）
async def process_slide_with_chat(
    prompt_item: ImagePrompt,
    chat_session,
    design_context: Any = None,
    session_id: str | None = None,  # セッションIDでGCSフォルダ分け
) -> ImagePrompt:
    """
    Helper function to process a single slide using a chat session for context carryover.
    
    Unlike process_single_slide(), this function uses an existing chat session
    where the SDK automatically maintains conversation history.
    
    Args:
        prompt_item (ImagePrompt): The prompt object containing the image generation instruction.
        chat_session: The chat session object from create_image_chat_session().
        design_context: DesignContext with layout-based template images (optional).
        
    Returns:
        ImagePrompt: Updated prompt item with `generated_image_url` populated.
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
        
        # === Reference Image (Template) ===
        reference_image_bytes = None
        if design_context:
            layout_ref = design_context.get_template_image_for_layout(layout_type)
            if layout_ref:
                reference_image_bytes = layout_ref
                logger.info(f"[Chat] Using template image for layout '{layout_type}'")
        
        logger.info(f"[Chat] Generating image {prompt_item.slide_number} via chat session...")
        
        # 1. Generate Image via Async Chat Session
        # Chat session maintains context from previous messages automatically
        image_bytes = await send_message_for_image_async(
            chat_session,
            final_prompt,
            reference_image=reference_image_bytes
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
        
        # ThoughtSignature は Chat 方式では使わない（履歴がセッションで管理されるため）
        prompt_item.thought_signature = ThoughtSignature(
            seed=0,  # Chatモードではシードは不使用
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


async def visualizer_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Node for the Visualizer agent. Responsible for generating slide images.

    This node executes the following complex logic:
    1. **Context Preparation**: Gathers instructions and previous artifacts.
    2. **Edit Mode Detection**: Identifies if this is a modification of existing slides.
    3. **Prompt Generation**: Uses the LLM to generate image prompts (ImagePrompt schema).
    4. **Anchor Strategy (Visual Consistency)**:
        - **Strategy T (Template)**: Uses PPTX template images per layout_type (NEW - highest priority).
        - **Strategy A (Preferred)**: Generates a dedicated 'Style Anchor' image first, then uses it as a reference for all slides.
        - **Strategy B (Reuse)**: Reuses an existing anchor from a previous run (Deep Edit).
        - **Strategy C (Fallback)**: Uses the first slide as the anchor if no dedicated style is defined.
    5. **Parallel Execution**: Generates images concurrently using `asyncio.gather` with a semaphore.

    Args:
        state (State): Current graph state.

    Returns:
        Command[Literal["supervisor"]]: Route to supervisor (via reviewer) with generated artifacts.
    """
    logger.info("Visualizer starting task")
    # Find the current in-progress step for this agent
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "visualizer"
        )
    except StopIteration:
        logger.error("Visualizer called but no in_progress step found.")
        return Command(goto="supervisor", update={})
    
    # [NEW] Get DesignContext from state
    design_context = state.get("design_context")
    
    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"

    # [NEW] Inject Design Direction from Planner
    design_dir = current_step.get('design_direction')
    if design_dir:
        context += f"\n\n[Design Direction from Planner]:\n{design_dir}\n"


    # [NEW] Inject design context information into prompt
    if design_context:
        available_layouts = ", ".join([l.layout_type for l in design_context.layouts])
        color_context = f"""

## Template Design Context
- Primary colors: {design_context.color_scheme.accent1}, {design_context.color_scheme.accent2}
- Background: {design_context.color_scheme.dk1}
- Text: {design_context.color_scheme.lt1}
- Font style: {design_context.font_scheme.major_latin} (headings)
- Available layout types: {available_layouts}

## IMPORTANT: Layout Type Selection
For each slide, you MUST specify the appropriate `layout_type` based on the slide's purpose:
- "title_slide": Opening or closing slides with large centered title
- "section_header": Section dividers
- "comparison": Side-by-side comparison slides
- "title_and_content": Standard content slides with title and bullet points
- "picture_with_caption": Image-focused slides
- "blank": Full-bleed visuals without text areas
- "other": Custom layouts

The template image for each layout will be automatically used as a reference image.
"""
        context = context + color_context

    # === Phase 3: Deep Edit Workflow (Thought Signature) ===
    # Check for previous visualizer outputs to enable "Edit Mode"
    previous_generations: list[dict] = []
    for key, json_str in state.get("artifacts", {}).items():
        if key.endswith("_visual"):
            try:
                data = json.loads(json_str)
                if "prompts" in data:
                    previous_generations.extend(data["prompts"])
            except Exception:
                pass
    
    # [REMOVED] Check for previous Anchor URL
    # previous_anchor_url = None
    # ... logic removed ...
    
    if previous_generations:
        context += f"\n\n# PREVIOUS GENERATIONS (EDIT MODE)\nUser wants to modify these. Maintain consistency with seed/style if specified:\n{json.dumps(previous_generations, ensure_ascii=False, indent=2)}"
    
    # Build messages with prompt template
    messages = apply_prompt_template("visualizer", state)
    
    # [NEW] Multimodal Context Injection
    # Constructs a mix of text and image content for the LLM if template images are available.
    supervisor_content = [{"type": "text", "text": context}]
    
    if design_context:
        # Select representative image for style analysis (Title Slide -> Content -> First Available)
        target_layout = "title_slide"
        # Fallback to title_and_content
        if "title_and_content" in design_context.layout_images or "title_and_content" in design_context.layout_images_base64:
            target_layout = "title_and_content"
        # Fallback to first available
        elif design_context.layout_images:
            target_layout = list(design_context.layout_images.keys())[0]
        elif design_context.layout_images_base64:
            target_layout = list(design_context.layout_images_base64.keys())[0]

        image_url = design_context.layout_images.get(target_layout)
        # Check base64 map first for in-memory flow
        image_b64 = design_context.layout_images_base64.get(target_layout)

        if image_url:
            logger.info(f"Injecting template image (URL) for '{target_layout}' into Visualizer context.")
            supervisor_content.append({
                "type": "image_url",
                "image_url": {"url": image_url}
            })
        elif image_b64:
            logger.info(f"Injecting template image (Base64) for '{target_layout}' into Visualizer context.")
            supervisor_content.append({
                "type": "image_url",
                # LangChain Google GenAI generally accepts 'data:image/png;base64,...' 
                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
            })

    messages.append(HumanMessage(content=supervisor_content, name="supervisor"))
    
    # Use with_structured_output for automatic parsing (Gemini Controlled Generation)
    llm = get_llm_by_type(AGENT_LLM_MAP["visualizer"])
    structured_llm = llm.with_structured_output(VisualizerOutput)
    
    try:
        # with_structured_output returns parsed Pydantic object directly
        result: VisualizerOutput = structured_llm.invoke(messages)
        logger.info("✅ Visualizer output validated.")

        # Proceed with image generation
        prompts = result.prompts
        updated_prompts: list[ImagePrompt] = []
        anchor_bytes: bytes | None = None
        
        # [NEW] Generate session_id for GCS folder organization
        import uuid
        session_id = str(uuid.uuid4())
        logger.info(f"Generated session_id for GCS storage: {session_id}")

        
        # === [NEW] STRATEGY T: Template-based (Per-Layout Reference) ===
        # This is the highest priority strategy when design_context is available
        if design_context and design_context.layout_images_base64:
            logger.info("Using per-layout template images (Strategy T)")
            
            # Parallel processing with layout-based reference images
            semaphore = asyncio.Semaphore(settings.VISUALIZER_CONCURRENCY)
            
            async def constrained_task_template(prompt_item: ImagePrompt) -> ImagePrompt:
                async with semaphore:
                    # Pass design_context to select layout-specific reference image
                    return await process_single_slide(
                        prompt_item, 
                        previous_generations,
                        override_reference_bytes=None,  # Don't override - let design_context handle selection
                        design_context=design_context,
                    )
            
            tasks = [constrained_task_template(item) for item in prompts]
            if tasks:
                logger.info(f"Starting parallel generation for {len(tasks)} slides with per-layout templates...")
                updated_prompts = list(await asyncio.gather(*tasks))
        
        # === Existing Anchor Strategies (when no design_context) ===
        else:
            # === STRATEGY C (Modified): Sequential Generation ===
            # No anchor strategy. Visual consistency depends on "Visual style" text in prompt.
            # We process all slides sequentially or in parallel?
            # To maintain "Context Carryover" (Chat session), we must process sequentially if we want sharing.
            # However, without an anchor image, parallel is also fine if prompts are strong enough.
            # But the requirement is "Visual_style (text prompt) to unify".
            # The previous logic for sequential processing with chat session was robust for consistency.
            # Let's keep sequential processing for now as it's safe (Context Carryover).
            
            target_prompts = prompts
            
            if target_prompts:
                # Create an async chat session for sequential generation
                seed = random.randint(0, 2**31 - 1)
                chat_session = await create_image_chat_session_async(seed)
                logger.info(f"[Sequential] Starting sequential generation for {len(target_prompts)} slides with context carryover...")
                
                for idx, prompt_item in enumerate(target_prompts):
                    logger.info(f"[Sequential] Processing slide {idx + 1}/{len(target_prompts)}...")
                    processed = await process_slide_with_chat(
                        prompt_item,
                        chat_session,
                        design_context=design_context,
                        session_id=session_id,
                    )
                    updated_prompts.append(processed)
        
        # Update results
        # Sort by slide number just in case
        updated_prompts.sort(key=lambda x: x.slide_number)
        result.prompts = updated_prompts
        
        content_json = json.dumps(result.model_dump(), ensure_ascii=False, indent=2)
        logger.info(f"Visualizer generated {len(result.prompts)} image prompts with artifacts")
        result_summary = result.execution_summary
    except Exception as e:
        logger.error(f"Visualizer structured output failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"
    
    # Update result summary in plan
    current_step["result_summary"] = result_summary

    # Create UI-specific messages
    # 1. Result Summary
    result_message = AIMessage(
        content=f"Visualizer generated {len(result.prompts)} images.",
        additional_kwargs={
            "ui_type": "worker_result",
            "role": "visualizer",
            "status": "completed",
            "result_summary": result_summary
        },
        name="visualizer_ui"
    )

    # 2. Artifact Button
    artifact_message = AIMessage(
        content="Images Generated",
        additional_kwargs={
            "ui_type": "artifact_view",
            "artifact_id": f"step_{current_step['id']}_visual",
            "title": "Visual Assets",
            "icon": "Image",
            "preview_urls": [p.generated_image_url for p in result.prompts if p.generated_image_url]
        },
        name="visualizer_artifact"
    )

    return Command(
        update={
            "messages": [
                HumanMessage(content=settings.RESPONSE_FORMAT.format(role="visualizer", content=content_json), name="visualizer"),
                result_message,
                artifact_message
            ],
            "artifacts": _update_artifact(state, f"step_{current_step['id']}_visual", content_json),
            "plan": state["plan"]
        },
        goto="supervisor",
    )


def data_analyst_node(state: State) -> Command[Literal["supervisor"]]:
    """
    Node for the Data Analyst agent.
    
    Uses Code Execution for calculations and proceeds to Supervisor.
    """
    logger.info("Data Analyst starting task")
    # Find the current in-progress step for this agent
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "data_analyst"
        )
    except StopIteration:
        logger.error("Data Analyst called but no in_progress step found.")
        return Command(goto="supervisor", update={})

    context = f"Instruction: {current_step['instruction']}\n\nAvailable Artifacts: {json.dumps(state.get('artifacts', {}), default=str)}"

    # Build messages with prompt template
    messages = apply_prompt_template("data_analyst", state)
    messages.append(HumanMessage(content=context, name="supervisor"))

    # Enable Code Execution tool (correctly bind tools separately from generation_config)
    llm = get_llm_by_type(AGENT_LLM_MAP["data_analyst"])
    
    # Bind code_execution tool using correct format for LangChain Google GenAI
    llm_with_code_exec = llm.bind(tools=[{"code_execution": {}}])

    try:
        # Prompt explicitly enforces JSON structure in the text
        messages[-1].content += "\n\nIMPORTANT: After performing necessary calculations with code, you MUST output the final result in valid JSON format matching the DataAnalystOutput structure."
        
        response = llm_with_code_exec.invoke(messages)
        content = response.content
        
        # Handle multimodal list content (Gemini often returns list of parts)
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
                elif isinstance(part, str):
                    text_parts.append(part)
            content = "".join(text_parts)
        
        # Try parsing JSON from content (it might be wrapped in markdown or have thought traces)
        import re
        json_match = re.search(r"\{.*\}", content, re.DOTALL)
        if json_match:
            try:
                result = DataAnalystOutput.model_validate_json(json_match.group(0))
                content_json = result.model_dump_json() # Normalize
                logger.info(f"✅ Data Analyst generated {len(result.blueprints)} blueprints (Code Exec Enabled)")
            except Exception as e:
                logger.warning(f"Parsed JSON failed validation: {e}. Returning raw content.")
                content_json = json.dumps({"raw_output": content, "error": "Validation Failed"}, ensure_ascii=False)
        else:
             logger.warning("No JSON found in Data Analyst output (Code Exec used). Returning raw content.")
             content_json = json.dumps({"raw_output": content}, ensure_ascii=False)
             result_summary = "Performed analysis via code execution."

    except Exception as e:
        logger.error(f"Data Analyst failed: {e}")
        content_json = json.dumps({"error": str(e)}, ensure_ascii=False)
        result_summary = f"Error: {str(e)}"

    # Update result summary in plan
    current_step["result_summary"] = result_summary if 'result_summary' in locals() else "Analysis completed."
    if 'result' in locals() and hasattr(result, 'execution_summary'):
        current_step["result_summary"] = result.execution_summary

    # Create UI-specific messages
    # 1. Result Summary
    result_message = AIMessage(
        content="Data Analysis Completed.",
        additional_kwargs={
            "ui_type": "worker_result",
            "role": "data_analyst",
            "status": "completed",
            "result_summary": result_summary
        },
        name="data_analyst_ui"
    )

    # 2. Artifact Button
    artifact_message = AIMessage(
        content="Analysis Results",
        additional_kwargs={
            "ui_type": "artifact_view",
            "artifact_id": f"step_{current_step['id']}_data",
            "title": "Data Analysis Result",
            "icon": "BarChart"
        },
        name="data_analyst_artifact"
    )
    
    return Command(
        update={
            "messages": [
                HumanMessage(content=settings.RESPONSE_FORMAT.format(role="data_analyst", content=content_json), name="data_analyst"),
                result_message,
                artifact_message
            ],
            "artifacts": _update_artifact(state, f"step_{current_step['id']}_data", content_json),
            "plan": state["plan"]
        },
        goto="supervisor",
    )





async def supervisor_node(state: State) -> Command[Literal[*TEAM_MEMBERS, "__end__"]]:
    """
    Supervisor Node (Orchestrator).

    Manages the execution flow of the graph.
    - **Task Assignment**: Routes to the appropriate worker based on the current plan step.
    - **Progress Tracking**: Moves to the next step upon completion.
    - **Completion**: Routes to END when all steps are finished.

    Note: Reviewer removed - Workers now have Self-Critique built in.
    Workers return directly to Supervisor after completing their task + self-evaluation.

    Args:
        state (State): Current graph state.

    Returns:
        Command: Routing command to Worker or END.
    """
    logger.info("Supervisor evaluating state")
    
    plan = state.get("plan", [])
    
    # 1. Find the first non-complete step (or the currently executing one)
    # We look for 'in_progress' first. If none, we look for the first 'pending'.
    
    current_step_index = -1
    current_step = None
    
    # Check for in-progress step
    for i, step in enumerate(plan):
        if step["status"] == "in_progress":
            current_step_index = i
            current_step = step
            break
            
    # If no step is in progress, find the first pending step
    if current_step is None:
        for i, step in enumerate(plan):
            if step["status"] == "pending":
                current_step_index = i
                current_step = step
                break
    
    # If no pending or in-progress steps found, we are done
    if current_step is None:
        logger.info("All steps completed. Ending workflow.")
        return Command(goto="__end__")
        
    current_role = current_step["role"]
    
    # 2. Check logic:
    # If status is 'in_progress', check if artifacts are present to mark as complete.
    # If status is 'pending', mark as 'in_progress' and assign.
    
    if current_step["status"] == "in_progress":
        # Check if completed
        role_suffix_map = {
            "storywriter": "story",
            "visualizer": "visual",
            "researcher": "research",
            "data_analyst": "data"
        }
        suffix = role_suffix_map.get(current_role, "output")
        artifact_key = f"step_{current_step['id']}_{suffix}"
        
        artifacts = state.get("artifacts", {})
        step_completed = artifact_key in artifacts
        
        if step_completed:
            # Mark current step as complete
            plan[current_step_index]["status"] = "complete"
            logger.info(f"Step {current_step_index} ({current_role}) completed. Marking as complete.")
            
            # Recursive call or loop to find next step? 
            # Better to just return update and let supervisor run again (or loop locally)
            # But specific event emission is needed 
            
            # Find NEXT step (local logic to avoid multiple graph cycles if allowed)
            # But simple approach: Return update, Supervisor will run again and find next pending.
            return Command(
                goto="supervisor", 
                update={"plan": plan} # Save status change
            )
        else:
             # Still in progress (maybe returning from tool or intermediate step)
             # just route back to worker? Or if worker just finished it should have created artifact?
             # If we are here, it means worker returned but artifact not found? OR simply worker not finished?
             # Actually workers return directly to supervisor.
             # So if we are here and artifact is missing, we must re-assign to worker (retry).
             logger.info(f"Step {current_step_index} ({current_role}) in progress but no artifact. Re-assigning.")
             return Command(goto=current_role)

    elif current_step["status"] == "pending":
        # New task to start
        logger.info(f"Starting Step {current_step_index} ({current_role})")
        
        # Update status to in_progress
        plan[current_step_index]["status"] = "in_progress"
        
        # Emit Phase Change Event
        if current_step.get("title"):
            await adispatch_custom_event(
                "phase_change", 
                {
                    "id": str(current_step["id"]),
                    "title": current_step["title"],
                    "agent_name": current_role,
                    "description": current_step.get("description", "")
                }
            )
            
        return Command(
            goto=current_role,
            update={"plan": plan}
        )
        
    return Command(goto="__end__")





def planner_node(state: State) -> Command[Literal["supervisor", "__end__"]]:
    """Planner node - uses structured output for reliable JSON execution plan."""
    logger.info("Planner creating execution plan")
    
    # [NEW] Prepare context with serialized plan for <<plan>> placeholder
    context_state = deepcopy(state)
    context_state["plan"] = json.dumps(state.get("plan", []), ensure_ascii=False, indent=2)
    
    messages = apply_prompt_template("planner", context_state)
    
    # Use with_structured_output for automatic parsing (Gemini Controlled Generation)
    llm = get_llm_by_type("reasoning")
    structured_llm = llm.with_structured_output(PlannerOutput)
    
    try:
        # with_structured_output returns parsed Pydantic object directly
        result: PlannerOutput = structured_llm.invoke(messages)
        logger.info("✅ Planner output validated.")
        plan_data = [step.model_dump() for step in result.steps]
        
        logger.info(f"Plan generated with {len(plan_data)} steps (structured output).")
        return Command(
            update={
                "messages": [
                    HumanMessage(content=f"Plan Generated: {len(plan_data)} steps defined.", name="planner"),
                    AIMessage(
                        content="Plan Created",
                        additional_kwargs={
                            "ui_type": "plan_update",
                            "plan": plan_data,
                            "title": "Execution Plan",
                            "description": "The updated execution plan."
                        },
                        name="planner_ui"
                    )
                ],
                "plan": plan_data,
                # "current_step_index": 0, # REMOVED
                "artifacts": {}
            },
            goto="supervisor",
        )
    except Exception as e:
        logger.error(f"Planner structured output failed: {e}")
        return Command(
            update={"messages": [HumanMessage(content=f"Failed to generate a valid plan: {e}", name="planner")]},
            goto="__end__"
        )

async def coordinator_node(state: State) -> Command[Literal["planner", "supervisor", "__end__"]]:
    """
    Coordinator Node: Gatekeeper & UX Manager (HITL).
    
    Responsibilities:
    1. **Ambiguity Resolution**: Qualify user requests before handing off to Planner.
    2. **Feedback Handling**: Process user feedback after workflow completion.
    3. **Progress Notification**: Emit SSE events for user experience.
    
    Flow:
    - Initial request → Classify → Handoff to Planner or Chat
    - Returning with feedback → Route to Supervisor for revision
    """
    from langchain_core.callbacks.manager import adispatch_custom_event
    
    logger.info("Coordinator processing request")
    
    # --- Initial classification ---
    messages = apply_prompt_template("coordinator", state)
    logger.debug(f"Coordinator Messages: {messages}")
    response = get_llm_by_type(AGENT_LLM_MAP["coordinator"]).invoke(messages)
    content = response.content
    
    # [Fix] Handle multimodal content (list of dicts) from Gemini
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict) and "text" in part:
                text_parts.append(part["text"])
            elif isinstance(part, str):
                text_parts.append(part)
        content = "".join(text_parts)
    
    logger.debug(f"Coordinator response: {content}")

    if "handoff_to_planner" in content:
        logger.info("Handing off to planner detected.")
        
        # Emit planning phase start event
        await adispatch_custom_event(
            "phase_change",
            {
                "id": "planning",
                "title": "プラン作成中",
                "agent_name": "planner",
                "description": "タスクを分析し、実行計画を策定しています..."
            }
        )
        
        return Command(
            goto="planner",
            # update={"progress_phase": "planning"} # REMOVED
        )
    
    # --- 3. Simple chat response (no handoff) ---
    return Command(
        update={"messages": [HumanMessage(content=content, name="coordinator")]},
        goto="__end__"
    )




# === Parallel Researcher Nodes ===


# === Researcher Subgraph ===

def research_agent_node(state: dict) -> dict:
     """Legacy agent node wrapper if needed, but here we use research_worker_node logic inside the subgraph."""
     pass

def research_worker_node(state: ResearchSubgraphState) -> dict:
    """
    Worker node for executing a single research task.
    Receives only the specific 'task' payload via Send (mapped to state in a way, but Send passes payload).
    Wait, Send passes payload to the node. If the node is defined as (state: State), 
    the payload typically acts as the state or merges into it?
    
    In LangGraph Map-Reduce:
    Send("node_name", arg) will invoke the node with `arg` as the state-like input.
    """
    # When invoked via Send("research_worker", {"task": task}), the input is a dict.
    # We cast it for type checking manually.
    task: ResearchTask = state.get("task")
    if not task:
        logger.warning("Research Worker received empty task")
        return {"internal_research_results": []}

    logger.info(f"Worker executing task {task.id}: {task.perspective}")
    
    try:
        # Use direct LLM call with Native Grounding (replacing legacy research_agent)
        from src.prompts.template import load_prompt_markdown
        system_prompt = load_prompt_markdown("researcher")
        
        instruction = (
            f"You are investigating: '{task.perspective}'.\n"
            f"Requirement: {task.expected_output}\n"
        )
        if task.query_hints:
            instruction += f"Suggested Queries: {', '.join(task.query_hints)}"
            
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=instruction, name="dispatcher")
        ]
        
        # LLM with Native Grounding
        llm = get_llm_by_type("reasoning")
        grounding_tool = {'google_search': {}}
        llm_with_search = llm.bind(
            tools=[grounding_tool],
            generation_config={"response_modalities": ["TEXT"]}
        )
        
        response = llm_with_search.invoke(messages)
        content = response.content
        
        # Handle multimodal list content
        if isinstance(content, list):
            text_parts = []
            for part in content:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
                elif isinstance(part, str):
                    text_parts.append(part)
            content = "".join(text_parts)
        
        res = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=content,
            sources=[], 
            confidence=1.0
        )
        return {"internal_research_results": [res]}
        
    except Exception as e:
        logger.error(f"Worker failed task {task.id}: {e}")
        err_res = ResearchResult(
            task_id=task.id,
            perspective=task.perspective,
            report=f"## Error\nInvestigation failed: {str(e)}",
            sources=[],
            confidence=0.0
        )
        return {"internal_research_results": [err_res]}


def research_manager_node(state: ResearchSubgraphState) -> Command[Literal["research_worker", "__end__"]]:
    """
    Manager Node (Orchestrator):
    1. Decompose: If no tasks yet, generate them using LLM.
    2. Fan Out: Send tasks to Workers.
    3. Aggregate: If results match task count, summarize and exit.
    """
    logger.info(f"Research Manager active. Decomposed: {state.get('is_decomposed', False)}")

    # Find the current in-progress step for this agent
    try:
        step_index, current_step = next(
            (i, step) for i, step in enumerate(state["plan"]) 
            if step["status"] == "in_progress" and step["role"] == "researcher"
        )
    except StopIteration:
        logger.error("Research Manager called but no in_progress step found.")
        return Command(goto="__end__", update={})
    internal_tasks = state.get("internal_research_tasks", [])
    results = state.get("internal_research_results", [])

    # === Phase 1: Decomposition ===
    if not state.get("is_decomposed"):
        logger.info("Manager: Decomposing research step...")
        
        # Use Topic Analyzer LLM
        # We manually load the prompt for clean execution
        from src.prompts.template import load_prompt_markdown
        base_prompt = load_prompt_markdown("research_topic_analyzer")
        full_content = f"{base_prompt}\n\nUser Instruction: {current_step['instruction']}"
        
        llm = get_llm_by_type("reasoning")
        structured_llm = llm.with_structured_output(ResearchTaskList)
        
        try:
            qa_result: ResearchTaskList = structured_llm.invoke(full_content)
            tasks = qa_result.tasks
            if not tasks:
                 raise ValueError("No tasks generated")
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Fallback to single task.")
            tasks = [
                ResearchTask(
                   id=1, 
                   perspective="General Investigation", 
                   query_hints=[], 
                   priority="high", 
                   expected_output="Detailed report."
                )
            ]

        logger.info(f"Manager: Generated {len(tasks)} parallel tasks.")
        
        sends = [Send("research_worker", {"task": t}) for t in tasks]
        return Command(
             update={"internal_research_tasks": tasks, "is_decomposed": True, "internal_research_results": []},
             goto=sends
        )

    # === Phase 2: Check & Aggregate ===
    # Check if all tasks have results
    if len(results) >= len(internal_tasks):
        logger.info("Manager: All tasks completed. Aggregating.")
        results.sort(key=lambda x: x.task_id)
        
        # 3. Create Aggregation Result
        # Simple concatenation or summary?
        # Ideally, we should summarize the findings into one cohesive report or just list them.
        # For simplicity, we create a JSON artifact containing all reports.
        
        aggregated_content = {
            "tasks": [t.model_dump() for t in internal_tasks],
            "results": [r.model_dump() for r in results]
        }
        content_json = json.dumps(aggregated_content, ensure_ascii=False)
        
        summary_text = f"Completed {len(results)} research tasks. Perspectives: {', '.join([r.perspective for r in results])}"
        current_step["result_summary"] = summary_text

        # 4. Finish
        logger.info(f"Research Manager finished. Aggregated {len(results)} results.")
        
        # Create UI-specific messages
        # 1. Result Summary
        result_message = AIMessage(
            content=f"Research Completed ({len(results)} tasks).",
            additional_kwargs={
                "ui_type": "worker_result",
                "role": "researcher", 
                "status": "completed",
                "result_summary": summary_text
            },
            name="researcher_ui"
        )
        
        # 2. Artifact Button
        artifact_message = AIMessage(
            content="Research Report",
            additional_kwargs={
                "ui_type": "artifact_view",
                "artifact_id": f"step_{current_step['id']}_research",
                "title": "Research Report",
                "icon": "BookOpen"
            },
            name="researcher_artifact"
        )

        return Command(
            goto="supervisor",
            update={
                "artifacts": _update_artifact(state, f"step_{current_step['id']}_research", content_json),
                "messages": [
                    result_message,
                    artifact_message
                ],
                "internal_research_tasks": [], # Reset
                "internal_research_results": [],
                "is_decomposed": False,
                "plan": state["plan"]
            }
        )
    
    # If not all results are in yet, do nothing and wait for other workers (implicitly)
    logger.info(f"Manager: Waiting for workers. {len(results)}/{len(internal_tasks)} completed.")
    return Command(update={})


def build_researcher_subgraph():
    """Builds the encapsulated researcher subgraph."""
    workflow = StateGraph(ResearchSubgraphState)
    
    workflow.add_node("manager", research_manager_node)
    workflow.add_node("research_worker", research_worker_node)
    
    workflow.add_edge(START, "manager")
    workflow.add_edge("research_worker", "manager")
    
    return workflow.compile()

