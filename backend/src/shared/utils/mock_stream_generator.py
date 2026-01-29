
import asyncio
import uuid
from typing import AsyncGenerator
from src.shared.utils.sse_formatter import DataStreamFormatter

async def generate_mock_stream() -> AsyncGenerator[str, None]:
    """
    Generates a sequence of mock events simulating a full agent workflow.
    Used for verifying frontend handling of all Datapart types.
    """
    formatter = DataStreamFormatter()
    
    # 1. Pre-processing status (Simulating PPTX analysis)
    yield formatter.data_part("status", {"message": "Analyzing template...", "phase": "preprocessing"})
    await asyncio.sleep(0.1)

    # 2. Workflow Start
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    yield formatter.data_part("data-workflow-start", {"runId": run_id})
    
    # 3. Phase Change
    yield formatter.data_part("data-phase-change", {
        "id": f"phase_research",
        "title": "Phase: Research",
        "description": "Gathering information..."
    })
    
    # 4. Agent Start (Researcher)
    step_id_research = f"step_{uuid.uuid4().hex[:8]}"
    yield formatter.step_start(step_id_research)
    yield formatter.data_part("data-agent-start", {
        "id": step_id_research,
        "agent_name": "researcher",
        "title": "Researcher Agent",
        "description": "Searching for relevant data..."
    })
    
    # 5. Reasoning Stream
    rs_id = f"rs_{uuid.uuid4().hex[:8]}"
    yield formatter.reasoning_start(rs_id)
    yield formatter.reasoning_delta(rs_id, "Thinking about search query...")
    yield formatter.reasoning_delta(rs_id, " Deciding to use Google Search.")
    yield formatter.reasoning_end(rs_id)
    
    # 6. Tool Call (DataAnalyst style, but inside Researcher for demo)
    tool_call_id = f"call_{uuid.uuid4().hex[:8]}"
    yield formatter.tool_call(tool_call_id, "google_search", {"query": "LangChain streaming"})
    yield formatter.data_part("data-code-execution", {
        "toolCallId": tool_call_id,
        "code": "search_tool.run('LangChain streaming')",
        "language": "python"
    })
    
    # 7. Tool Result
    yield formatter.tool_result(tool_call_id, "Found documentation for Vercel AI SDK.")
    yield formatter.data_part("data-code-output", {
        "toolCallId": tool_call_id,
        "result": "Found documentation..."
    })
    
    # 8. Plan Update (Supervisor)
    yield formatter.data_part("data-plan-update", {
        "id": "plan_1",
        "steps": [
            {"id": "s1", "title": "Research", "status": "active"},
            {"id": "s2", "title": "Draft content", "status": "pending"}
        ]
    })
    
    # 9. Text Stream (Message)
    msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    yield formatter.text_start(msg_id)
    yield formatter.text_delta(msg_id, "I found some info. ")
    yield formatter.text_delta(msg_id, "Proceeding to draft.")
    yield formatter.text_end(msg_id)
    
    # 10. Agent End (Researcher)
    yield formatter.step_finish(step_id_research)
    yield formatter.data_part("data-agent-end", {"status": "completed", "stepId": step_id_research})
    
    # 11. Agent Start (Visualizer)
    step_id_viz = f"step_{uuid.uuid4().hex[:8]}"
    yield formatter.step_start(step_id_viz)
    yield formatter.data_part("data-agent-start", {
        "id": step_id_viz,
        "agent_name": "visualizer",
        "title": "Slide Visualizer",
        "description": "Generating slides..."
    })
    
    # 12. Slide Outline
    yield formatter.data_part("data-slide_outline", {
        "slides": [
            {"title": "Introduction", "point": "Overview"},
            {"title": "Deep Dive", "point": "Details"}
        ]
    })
    
    # 13. Visualizer Progress
    yield formatter.data_part("data-visualizer-progress", {
        "slide_number": 1,
        "image_url": "http://mock/slide1.png",
        "title": "Introduction"
    })
    
    # 14. Artifact Ready (Slide Deck)
    yield formatter.data_part("data-artifact-ready", {
        "id": "deck_final",
        "type": "application/vnd.google-apps.presentation",
        "title": "Final Presentation.pptx",
        "kind": "slide_deck",
         "content": {"url": "http://mock/deck.pptx"}
    })
    
    # 15. File Part (Image Preview)
    yield formatter.file_part("http://mock/slide1.png", "image/png")
    
    # 16. Title Generation
    yield formatter.data_part("data-title-generated", {
        "title": "Streaming Verification Session",
        "thread_id": "thread_123"
    })
    
    # 17. Finish
    yield formatter.finish()
