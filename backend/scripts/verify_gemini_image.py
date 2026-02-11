import os
import sys
import logging
from google import genai
from google.genai import types

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def verify_image_generation(api_key: str):
    # For AI Studio, vertexai=False (default)
    client = genai.Client(api_key=api_key)
    model_id = "gemini-3-pro-image-preview"
    
    print(f"Testing model: {model_id} via AI Studio...")
    
    contents = ["A beautiful landscape with mountains and a lake at sunset, professional photography style."]
    
    # Configure generation capabilities for image output
    config = types.GenerateContentConfig(
        response_modalities=['IMAGE'],
        image_config=types.ImageConfig(
            aspect_ratio="16:9",
            image_size="2K"
        )
    )
    
    try:
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config=config,
        )
        
        # Log response structure for debugging
        logger.debug(f"Response: {response}")

        if response.candidates:
            candidate = response.candidates[0]
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.inline_data:
                        image_data = part.inline_data.data
                        output_path = "scripts/test_image.png"
                        with open(output_path, "wb") as f:
                            f.write(image_data)
                        print(f"Success! Image saved as {output_path}")
                        return True
        
        print("Failure: No image data in response.")
        print(f"Response: {response}")
        return False
        
    except Exception as e:
        print(f"Error during generation: {e}")
        return False

if __name__ == "__main__":
    # Provided API Key
    API_KEY = "AIzaSyD3kwDYHPsj9QpTPDRmyh-_EBTUTYEF5rw"
    success = verify_image_generation(API_KEY)
    if not success:
        sys.exit(1)
