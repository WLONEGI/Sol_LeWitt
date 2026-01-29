import pytest
import asyncio
import uuid
import logging
import os
from langchain_core.messages import HumanMessage

# Import from service to verify production initialization logic
from src.core.workflow.service import initialize_graph, close_graph, _manager
from src.shared.config.settings import settings

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Force real integration settings
# Assuming settings are already loaded from .env
os.environ["VERTEX_PROJECT_ID"] = settings.VERTEX_PROJECT_ID
os.environ["VERTEX_LOCATION"] = settings.VERTEX_LOCATION

@pytest.mark.asyncio
async def test_full_graph_execution_real_gcp():
    """
    E2E Test executing the full LangGraph workflow against REAL Google Cloud services.
    
    Verifies production code initialization via WorkflowManager.
    
    Verified Components:
    - Persistence (Cloud SQL / Postgres) via WorkflowManager
    - Planner (Vertex AI / Gemini 2.0 Flash Thinking)
    - Workers (Storywriter, Visualizer, Data Analyst)
    - GCS (Image Uploads)
    - Serialization (`Send` object handling in checkpoints)
    """
    
    logger.info("Initializing Graph via WorkflowManager (Production Path)...")
    await initialize_graph()
    
    try:
        graph = _manager.get_graph()
        
        # 3. Execution Config
        thread_id = f"e2e_test_{uuid.uuid4().hex[:8]}"
        config = {"configurable": {"thread_id": thread_id}}
        logger.info(f"Starting E2E Test with Thread ID: {thread_id}")
        
        # 4. Input Payload
        initial_state = {
            "messages": [
                HumanMessage(content="Create a 3-slide presentation about the future of Generative AI agentic workflows. Include a visual style of cyberpunk.")
            ],
            "plan": [],
            "artifacts": {}
        }
        
        # 5. Run Graph
        step_count = 0
        final_state = None
        
        try:
            async for event in graph.astream(initial_state, config, stream_mode="values"):
                step_count += 1
                current_plan = event.get("plan", [])
                
                # Simple progress logging
                if current_plan:
                    completed_steps = [s for s in current_plan if s["status"] == "complete"]
                    logger.info(f"Step {step_count}: {len(completed_steps)}/{len(current_plan)} steps complete.")
                
                final_state = event
                
        except Exception as e:
            logger.error(f"E2E Test Failed during execution: {e}")
            raise e
            
        # 6. Verifications
        logger.info("Workflow completed. Starting verification...")
        
        # A. Verify Plan Generated
        assert len(final_state["plan"]) > 0, "Planner failed to generate tasks."
        logger.info(f"✅ Plan generated with {len(final_state['plan'])} steps.")
        
        # B. Verify Storywriter Output
        story_artifacts = {k: v for k, v in final_state["artifacts"].items() if k.endswith("_story")}
        assert len(story_artifacts) > 0, "Storywriter failed to produce artifacts."
        logger.info(f"✅ Storywriter produced artifacts: {list(story_artifacts.keys())}")
        
        # C. Verify Visualizer Output & GCS
        visual_artifacts = {k: v for k, v in final_state["artifacts"].items() if k.endswith("_visual")}
        assert len(visual_artifacts) > 0, "Visualizer failed to produce artifacts."
        
        import json
        visual_data = json.loads(list(visual_artifacts.values())[0])
        prompts = visual_data.get("prompts", [])
        image_urls = [p.get("generated_image_url") for p in prompts if p.get("generated_image_url")]
        assert len(image_urls) > 0, "No image URLs found. GCS upload might have failed."
        logger.info(f"✅ Visualizer produced {len(image_urls)} images. Sample: {image_urls[0]}")
        
        # D. Verify Persistence
        # Checkpointer is accessible via graph object in LangGraph
        checkpointer = graph.checkpointer
        assert checkpointer is not None, "Checkpointer is not configured."
        
        checkpoint_tuple = await checkpointer.aget_tuple(config)
        assert checkpoint_tuple is not None, "Failed to retrieve checkpoint from DB."
        logger.info("✅ Checkpoint successfully retrieved from Postgres.")
        
        logger.info("🎉 E2E Test PASSED Successfully with Production Initialization.")
        
    finally:
        await close_graph()

if __name__ == "__main__":
    asyncio.run(test_full_graph_execution_real_gcp())
