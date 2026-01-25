import os
import sys
import json
import logging
from dotenv import load_dotenv

# Ensure the src directory is in the python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow import run_agent_workflow

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    # Load environment variables
    load_dotenv()

    # Check for critical env vars
    if not os.getenv("VERTEX_PROJECT_ID"):
        logger.error("VERTEX_PROJECT_ID not found in environment variables.")
        print("Please ensure your .env file is set up correctly with VERTEX_PROJECT_ID.")
        return

    print("Starting E2E Test for Image Generation...")
    print("Target: Backend LangGraph Workflow -> Visualizer -> Vertex AI -> GCS")
    
    # Define a prompt that explicitly requests image generation
    # Include Audience and Goal to satisfy Coordinator's qualification check
    user_input = "Create a 2-slide pitch deck for Technical Engineers about 'Future of AI Agents'. The goal is to explain the evolution from Chatbots to Autonomous Agents. Please include futuristic illustrations."
    
    try:
        # Run the workflow
        print(f"Input: {user_input}")
        print("Running workflow... (this may take a minute)")
        
        result = run_agent_workflow(user_input, debug=True)
        
        # Verify results
        print("\n=== Final Plan & Summaries ===")
        for step in result.get("plan", []):
            print(f"Step {step['id']} ({step['role']}): {step['status']}")
            print(f"  Summary: {step.get('result_summary')}")

        artifacts = result.get("artifacts", {})
        visual_artifacts = {k: v for k, v in artifacts.items() if k.endswith("_visual")}
        
        if not visual_artifacts:
            logger.error("❌ No visualizer artifacts found! The Visualizer node may not have run.")
            return

        print("\n=== Verified Generated Images ===")
        found_images = False
        
        for key, value in visual_artifacts.items():
            try:
                data = json.loads(value)
                prompts = data.get("prompts", [])
                
                # Check for Anchor Image
                if "anchor_image_url" in data and data["anchor_image_url"]:
                     print(f"✅ Anchor Image: {data['anchor_image_url']}")
                
                for p in prompts:
                    slide_num = p.get("slide_number")
                    img_url = p.get("generated_image_url")
                    
                    if img_url:
                        found_images = True
                        print(f"✅ Slide {slide_num}: {img_url}")
                        
                        # Basic validation of URL structure
                        if "storage.googleapis.com" not in img_url:
                            logger.warning(f"⚠️ URL does not look like standard GCS: {img_url}")
                    else:
                        logger.warning(f"❌ Slide {slide_num}: No image URL generated for this slide.")
                        
            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON for artifact {key}")

        if found_images:
            print("\n🎉 E2E Test Passed: Images were generated and URLs returned.")
        else:
            print("\n❌ E2E Test Failed: Visualizer ran but no images were found.")

    except Exception as e:
        logger.error(f"E2E Test Exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
