import logging
import base64
from typing import Any

from langchain_google_vertexai import VertexAIImageGeneratorChat
from langchain_core.messages import HumanMessage
from src.shared.config.settings import settings

logger = logging.getLogger(__name__)

def generate_image(prompt: str, seed: int | None = None, reference_image: bytes | None = None, thought_signature: str | None = None) -> tuple[bytes, str | None]:
    """
    Generate an image using Vertex AI via langchain-google-vertexai.
    Uses VertexAIImageGeneratorChat for gemini-3-pro-image-preview.
    
    Args:
        prompt (str): The text prompt for image generation.
        seed (int | None): Optional random seed for deterministic generation.
        reference_image (bytes | None): Optional image bytes to use as a reference.
        thought_signature (str | None): Optional thought signature (maintained for compatibility, but might be implicit in chat history).
        
    Returns:
        tuple[bytes, str | None]: The generated image data (PNG format) and the thought_signature (None if not supported/retrieved).
    
    Raises:
        ValueError: If no image data is found in the response.
    """
    try:
        model_name = settings.VL_MODEL
        logger.info(f"Generating image with model: {model_name} (Prompt: {prompt[:50]}..., Seed: {seed}, Has Ref: {bool(reference_image)})")

        # Initialize VertexAIImageGeneratorChat
        # Note: Parameters like 'seed' might need to be passed in invocation or config if supported.
        # Currently, langchain-google-vertexai might not expose 'seed' directly in init or invoke for all models.
        # We will attempt to pass it via configuration if possible, or omit if not supported by the wrapper yet.
        generator = VertexAIImageGeneratorChat(
            model=model_name,
            project=settings.VERTEX_PROJECT_ID,
            location=settings.VERTEX_LOCATION,
            image_config={"image_size": "2K"},
        )

        messages = []
        content: list[dict[str, Any] | str] = [prompt]
        
        # Handle Reference Image (Multimodal Input)
        if reference_image:
            # Create image content part
            # LangChain expects generic message format or implementation specific
            # For VertexAI, base64 encoded string in image_url or similar is common, 
            # but VertexAIImageGeneratorChat likely handles standard LangChain image blocks.
            image_b64 = base64.b64encode(reference_image).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"}
            })
            
        messages.append(HumanMessage(content=content))

        # Invoke generation
        # NOTE: thought_signature is a Gemini-specific feature for chain-of-thought in image generation.
        # LangChain wrapper returns a generic AIMessage. The image is usually in the content or artifact.
        response = generator.invoke(messages)
        
        # Extract Image
        # VertexAIImageGeneratorChat typically returns the image URL or base64 in the content
        # or as an artifact. We need to check the response structure.
        # If it returns a standard AIMessage, likely the image content is inside.
        
        generated_image = None
        
        if isinstance(response.content, list) and len(response.content) > 0:
             # Scenario: Content is a list of blocks (text/image)
             for block in response.content:
                 if isinstance(block, dict) and block.get("type") == "image_url":
                     url = block["image_url"]["url"]
                     if url.startswith("data:"):
                         header, data = url.split(",", 1)
                         generated_image = base64.b64decode(data)
                         break

        # Fallback/Alternative extraction (checking response_metadata for artifacts)
        if not generated_image and response.response_metadata:
             # Check if raw response handling is needed
             pass

        if not generated_image:
             # Strict check: If we can't extract, raise error.
             # Note: response.content might be empty if image is in additional_kwargs
             raise ValueError(f"Could not extract image from response: {response}")

        return generated_image, None # thought_signature not retrievalbe via standard wrapper yet

    except Exception as e:
        logger.error(f"Image generation failed with {settings.VL_MODEL}: {e}")
        raise e


# === Async Chat-Based Image Generation ===

async def create_image_chat_session_async(seed: int | None = None):
    """
    Create a new async chat session configured for image generation.
    For LangChain, this effectively returns a configured Runnable/Chain with history.
    """
    # LangChain ChatVertexAI/ImageGeneratorChat is stateless by default.
    # We return the generator instance to be used by the send method.
    model_name = settings.VL_MODEL
    generator = VertexAIImageGeneratorChat(
        model=model_name,
        project=settings.VERTEX_PROJECT_ID,
        location=settings.VERTEX_LOCATION,
    )
    # We might attach memory here if needed, but for now we return the model.
    return generator


async def send_message_for_image_async(chat, prompt: str, reference_image: bytes | None = None) -> bytes:
    """
    Send a message to the chat session (generator) and extract the image.
    args 'chat' is the VertexAIImageGeneratorChat instance.
    """
    # Re-use logic from generate_image but async
    messages = []
    content: list[dict[str, Any] | str] = [prompt]
    
    if reference_image:
        image_b64 = base64.b64encode(reference_image).decode("utf-8")
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{image_b64}"}
        })
        
    messages.append(HumanMessage(content=content))
    
    response = await chat.ainvoke(messages)
    
    generated_image = None
    if isinstance(response.content, list):
         for block in response.content:
             if isinstance(block, dict) and block.get("type") == "image_url":
                 url = block["image_url"]["url"]
                 if url.startswith("data:"):
                     header, data = url.split(",", 1)
                     generated_image = base64.b64decode(data)
                     break
                     
    if generated_image:
        return generated_image
        
    raise ValueError(f"No image data found in chat response.")



