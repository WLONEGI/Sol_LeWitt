import logging
import base64
from typing import Any, Optional

from google import genai
from google.genai import types

from src.shared.config.settings import settings

logger = logging.getLogger(__name__)

def _get_client() -> genai.Client:
    """Initialize and return the GenAI client."""
    return genai.Client(
        vertexai=True,
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION
    )

def generate_image(
    prompt: str, 
    seed: int | None = None, 
    reference_image: str | bytes | None = None, 
    thought_signature: str | None = None, 
    aspect_ratio: str | None = None
) -> tuple[bytes, str | None]:
    """
    Generate an image using Vertex AI via google-genai SDK.
    Uses gemini-3-pro-image-preview.
    
    Args:
        prompt (str): The text prompt for image generation.
        seed (int | None): Optional random seed.
        reference_image (str | bytes | None): Optional GCS URI (gs://...) or image bytes to use as a reference.
        thought_signature (str | None): Optional thought signature.
        aspect_ratio (str | None): Optional aspect ratio (e.g., "16:9", "1:1").
        
    Returns:
        tuple[bytes, str | None]: The generated image data (PNG format) and the thought_signature.
    
    Raises:
        ValueError: If no image data is found in the response.
    """
    try:
        model_name = settings.VL_MODEL
        logger.info(f"Generating image with model: {model_name} (Prompt len: {len(prompt)}, Ref: {bool(reference_image)}, AR: {aspect_ratio})")

        client = _get_client()

        contents = [prompt]
        if reference_image:
            if isinstance(reference_image, str) and reference_image.startswith("gs://"):
                contents.append(types.Part.from_uri(uri=reference_image, mime_type="image/png"))
            elif isinstance(reference_image, bytes):
                contents.append(types.Part.from_bytes(data=reference_image, mime_type="image/png"))
            else:
                # Handle public HTTPS URLs by adding them as text parts or raise warning
                # Gemini Pro Vision/Flash can handle public URLs if passed correctly, 
                # but for generate_content image generation, GCS URI is preferred.
                logger.warning(f"Reference image provided is neither GCS URI nor bytes: {type(reference_image)}")
                contents.append(reference_image) if isinstance(reference_image, str) else None

        # Configure generation capabilities
        image_config = None
        if aspect_ratio:
            image_config = types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size="2K" # Defaulting to 2K as per user snippet
            )
            
        config = types.GenerateContentConfig(
            response_modalities=['IMAGE'],
            image_config=image_config if image_config else None
        )

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=config,
        )

        # Check for errors
        if not response.candidates:
             raise ValueError("No candidates returned from generation.")
             
        if response.candidates[0].finish_reason != types.FinishReason.STOP:
            reason = response.candidates[0].finish_reason
            # Sometimes finish_reason might be different but content is present, but for safety:
            if reason != types.FinishReason.STOP:
                 logger.warning(f"Generation finished with reason: {reason}")
            # We continue to check for content.

        generated_image = None
        extracted_thought_signature = None
        
        # Extract thought_signature from candidate if available
        candidate = response.candidates[0]
        if hasattr(candidate, 'thought_signature') and candidate.thought_signature:
            extracted_thought_signature = candidate.thought_signature
            logger.debug("Extracted thought_signature from response candidate.")
        
        # Iterate through parts to find the image
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if part.inline_data:
                    generated_image = part.inline_data.data
                    break
        
        if not generated_image:
             raise ValueError(f"Could not extract image from response. Response: {response}")

        return generated_image, extracted_thought_signature

    except Exception as e:
        logger.error(f"Image generation failed with {settings.VL_MODEL}: {e}")
        raise e


# === Async Chat-Based Image Generation ===

async def create_image_chat_session_async(seed: int | None = None, aspect_ratio: str | None = None):
    """
    Create a new async chat session configured for image generation.
    Returns the client and configuration to be used in send_message.
    """
    # Simply return the client as "chat" object for now, or a wrapper.
    # Since google-genai chat is different, we'll just return the client.
    return _get_client()


async def send_message_for_image_async(chat, prompt: str, reference_image: str | bytes | None = None) -> bytes:
    """
    Send a message to the chat session (generator) and extract the image.
    args 'chat' is the genai.Client instance.
    """
    # Assuming 'chat' is the client.
    # For now, we reuse the generate_content logic because true "chat" with image generation state 
    # might need client.chats.create() but the previous logic was stateless per call mostly.
    # If state is required, we need to manage history. 
    # Given the previous implementation was effectively stateless (langchain just invokes),
    # we will use generate_image logic here properly.
    
    # NOTE: The visualizer calls 'send_message_for_image_async' which implies it expects a chat-like behavior
    # but strictly for image generation.
    
    # We will just call the blocking generate_image in a thread for async compatibility 
    # OR use client.aio.models.generate_content if available.
    # google-genai DOES support async. 
    # But for simplicity and consistency with the main function, let's wrap the logic.
    
    # However, to be purely async:
    # client = chat
    # response = await client.aio.models.generate_content(...)
    # But `client` created above is synchronous `genai.Client`. 
    # We need `genai.Client` to be compatible? 
    # Actually, `genai.Client` has `aio` property? No, it's `from google import genai; client = genai.Client(...)`
    # The async client is separate? 
    # Docs: client.aio.models.generate_content
    
    import asyncio
    
    # Reuse the synchronous generate_image logic for now to ensure consistency, 
    # running in a separate thread to avoid blocking the event loop.
    
    result = await asyncio.to_thread(
        generate_image,
        prompt=prompt,
        reference_image=reference_image
    )
    return result[0]




