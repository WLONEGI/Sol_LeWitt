import pytest
import asyncio
import uuid
import logging
import os
import json
from langchain_core.messages import HumanMessage, AIMessage

# Import from service to verify production initialization logic
from src.core.workflow.service import initialize_graph, close_graph, _manager
from src.shared.config.settings import settings

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@pytest.fixture(autouse=True)
async def cleanup_workflow():
    """Ensure the workflow manager is closed after each test to avoid event loop issues."""
    yield
    await close_graph()

@pytest.mark.asyncio
async def test_langgraph_comprehensive_flow():
    """
    Run all 4 test cases in a single event loop to avoid 'bound to different event loop' errors
    while sharing the WorkflowManager singleton.
    """
    # Initialize graph once for the entire suite
    await initialize_graph()
    try:
        # Case 1: Basic Slide Creation
        logger.info(">>> RUNNING CASE 1: Basic Slide Creation")
        initial_state_1 = {
            "messages": [HumanMessage(content="Create a 2-slide presentation about the benefits of drinking water.")],
            "plan": [],
            "artifacts": {}
        }
        def verify_1(state):
            plan = state.get("plan", [])
            assert len(plan) >= 2
            roles = [s["role"] for s in plan]
            assert "storywriter" in roles
            assert "visualizer" in roles
            artifacts = state.get("artifacts", {})
            assert any("story" in k for k in artifacts.keys())
            assert any("visual" in k for k in artifacts.keys())
        await run_and_verify_flow_internal(initial_state_1, verify_1)

        # Case 2: Research-Integrated Flow
        logger.info(">>> RUNNING CASE 2: Research-Integrated Flow")
        initial_state_2 = {
            "messages": [HumanMessage(content="Create a slide about the top AI trends in 2024 based on recent news.")],
            "plan": [],
            "artifacts": {}
        }
        def verify_2(state):
            plan = state.get("plan", [])
            roles = [s["role"] for s in plan]
            assert "researcher" in roles
            artifacts = state.get("artifacts", {})
            assert any("research" in k for k in artifacts.keys())
        await run_and_verify_flow_internal(initial_state_2, verify_2)

        # Case 3: Data-Heavy Flow
        logger.info(">>> RUNNING CASE 3: Data-Heavy Flow")
        initial_state_3 = {
            "messages": [HumanMessage(content="Create a slide comparing the market share of top 5 smartphone brands in Q4 2023. Show it as a chart.")],
            "plan": [],
            "artifacts": {}
        }
        def verify_3(state):
            plan = state.get("plan", [])
            roles = [s["role"] for s in plan]
            assert "data_analyst" in roles
            artifacts = state.get("artifacts", {})
            assert any("data" in k for k in artifacts.keys())
        await run_and_verify_flow_internal(initial_state_3, verify_3)

        # Case 4: Interactive Chat
        logger.info(">>> RUNNING CASE 4: Interactive Chat")
        initial_state_4 = {
            "messages": [HumanMessage(content="Hello, who are you?")],
            "plan": [],
            "artifacts": {}
        }
        def verify_4(state):
            plan = state.get("plan", [])
            assert len(plan) == 0
            last_msg = state["messages"][-1]
            assert last_msg.name == "coordinator"
            assert len(last_msg.content) > 0
        await run_and_verify_flow_internal(initial_state_4, verify_4)

    finally:
        await close_graph()

async def run_and_verify_flow_internal(initial_state, verify_logic):
    """Internal helper to run and verify a flow using the already initialized global _manager."""
    graph = _manager.get_graph()
    thread_id = f"e2e_comp_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    
    logger.info(f"--- Starting Flow with Thread ID: {thread_id} ---")
    
    async for event in graph.astream(initial_state, config, stream_mode="values"):
        final_state = event
        
    state = await graph.aget_state(config)
    while state.next:
        logger.info(f"Graph interrupted at {state.next}. Resuming...")
        async for event in graph.astream(None, config, stream_mode="values"):
            final_state = event
        state = await graph.aget_state(config)
        
    if verify_logic:
        verify_logic(final_state)
    return final_state
