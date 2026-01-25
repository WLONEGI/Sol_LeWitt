import logging
import uuid
import json
from typing import Any, AsyncGenerator
# from langchain_community.adapters.openai import convert_message_to_dict
# from langgraph.checkpoint.memory import MemorySaver

from src.config import TEAM_MEMBERS
from src.config.settings import settings
from src.graph import build_graph

# Try importing Postgres dependencies
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    HAS_POSTGRES_DEPS = True
except ImportError:
    HAS_POSTGRES_DEPS = False


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def enable_debug_logging():
    """Enable debug level logging for more detailed execution information."""
    logging.getLogger("src").setLevel(logging.DEBUG)



class WorkflowManager:
    """
    Singleton manager for the LangGraph workflow and its resources (DB connection, Graph instance).
    Eliminates global variables and ensures safe initialization/cleanup.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
            cls._instance.pool = None
            cls._instance.graph = None
        return cls._instance

    async def initialize(self):
        """
        Initialize the graph with appropriate checkpointer.
        Idempotent: Safe to call multiple times, though usually called once at startup.
        """
        if self.initialized:
            logger.info("WorkflowManager already initialized.")
            return

        logger.info("Initializing WorkflowManager...")

        if not settings.POSTGRES_DB_URI:
            error_msg = "settings.POSTGRES_DB_URI is not set. Persistence is required."
            logger.critical(error_msg)
            raise ValueError(error_msg)

        if not HAS_POSTGRES_DEPS:
            error_msg = (
                "settings.POSTGRES_DB_URI is set but postgres dependencies "
                "(langgraph-checkpoint-postgres, psycopg_pool) are missing. "
                "Cannot establish persistence."
            )
            logger.critical(error_msg)
            raise ImportError(error_msg)

        logger.info("Initializing Postgres Checkpointer...")
        try:
            # Create connection pool
            connection_info = settings.POSTGRES_DB_URI.replace("postgresql+psycopg://", "postgresql://")
            
            # Cloud Run / Serverless optimized pool settings
            self.pool = AsyncConnectionPool(
                conninfo=connection_info,  
                min_size=1, 
                max_size=10, 
                open=False,
                timeout=30.0
            )
            await self.pool.open()
            
            # Setup checkpointer
            checkpointer = AsyncPostgresSaver(self.pool)
            await checkpointer.setup()
            
            # Build graph
            self.graph = build_graph(checkpointer=checkpointer)
            logger.info("✅ Graph initialized with AsyncPostgresSaver. Persistence enabled.")
            
        except Exception as e:
            logger.critical(f"❌ Failed to initialize Postgres persistence: {e}")
            logger.critical("Aborting startup to prevent state loss.")
            if self.pool:
                await self.pool.close()
            raise e

        self.initialized = True

    async def close(self):
        """Cleanup resources."""
        if self.pool:
            logger.info("Closing DB connection pool...")
            await self.pool.close()
            self.pool = None
        self.initialized = False
        logger.info("WorkflowManager shutdown complete.")

    def get_graph(self):
        """Return the initialized graph instance."""
        if not self.graph:
            raise RuntimeError("Graph not initialized. Call initialize() first.")
        return self.graph


# Expose singleton instance methods for existing API compatibility
_manager = WorkflowManager()

async def initialize_graph():
    await _manager.initialize()

async def close_graph():
    await _manager.close()

async def run_agent_workflow(
    user_input_messages: list[dict[str, Any]],
    debug: bool = False,
    thread_id: str | None = None,
    design_context: Any = None,
) -> AsyncGenerator[str, None]:
    """Run the agent workflow with the given user input."""
    if not user_input_messages:
        raise ValueError("Input could not be empty")

    if debug:
        enable_debug_logging()

    # Get graph from manager
    graph = _manager.get_graph()

    # Use provided thread_id or generate a new one
    if not thread_id:
        thread_id = str(uuid.uuid4())

    logger.info(f"Starting workflow with user input: {user_input_messages} (Thread ID: {thread_id})")
    
    if design_context:
        logger.info(f"DesignContext provided: {len(design_context.layouts)} layouts")

    # Workflow ID identifies this specific execution run
    workflow_id = str(uuid.uuid4())

    streaming_llm_agents = [*TEAM_MEMBERS, "planner", "coordinator"]

    # Configure persistence
    config = {"configurable": {"thread_id": thread_id}}

    input_state = {
        "messages": user_input_messages,
        "design_context": design_context,
    }

    # Helper to yield JSON string
    def _json_event(type_: str, content: Any = None, metadata: dict = {}) -> str:
        return json.dumps({
            "type": type_,
            "content": content,
            "metadata": metadata
        }, ensure_ascii=False)

    async for event in graph.astream_events(
        input_state,
        config=config,
        version="v2",
    ):
        kind = event.get("event")
        data = event.get("data")
        name = event.get("name")
        metadata = event.get("metadata")
        
        # Determine strict node name (e.g. "planner", "researcher")
        node = (
            ""
            if (metadata.get("checkpoint_ns") is None)
            else metadata.get("checkpoint_ns").split(":")[0]
        )
        langgraph_step = (
            ""
            if (metadata.get("langgraph_step") is None)
            else str(metadata["langgraph_step"])
        )
        run_id = "" if (event.get("run_id") is None) else str(event["run_id"])

        # 1. Agent Start/End Events
        if kind == "on_chain_start" and name in streaming_llm_agents:
            if name == "planner":
                # Special event for workflow start
                yield _json_event("workflow_start", metadata={
                    "workflow_id": workflow_id,
                    "thread_id": thread_id
                })
            
            yield _json_event("agent_start", metadata={
                "agent_name": name,
                "agent_id": f"{workflow_id}_{name}_{langgraph_step}"
            })

        elif kind == "on_chain_end" and name in streaming_llm_agents:
             # Check for Artifact Generation first
            output = data.get("output")
            artifact_update = None
            
            # Extract 'artifacts' from Command or dict
            if isinstance(output, dict): # Standard dict state update
                 artifact_update = output.get("artifacts")
            elif hasattr(output, "update"): # Command object
                 artifact_update = output.update.get("artifacts") if isinstance(output.update, dict) else None

            if artifact_update:
                for key, content in artifact_update.items():
                    # Determine Artifact Type based on key convention
                    art_type = "report" # default
                    if "_story" in key: art_type = "outline"
                    elif "_visual" in key: art_type = "image" # contains prompts and debug info
                    elif "_research" in key: art_type = "report"
                    elif "_data" in key: art_type = "report"
                    elif "_plan" in key: art_type = "plan"
                    
                    artifact_id = f"{workflow_id}_{key}"
                    
                    yield _json_event("artifact", content={
                        "id": artifact_id,
                        "type": art_type,
                        "title": f"Artifact: {key}",
                        "content": content,
                        "version": 1
                    }, metadata={"agent_name": name})

            # [NEW] Check for Messages update to extract metadata (sources)
            # This allows passing grounding metadata from nodes (like researcher) to the frontend
            messages_update = None
            if isinstance(output, dict):
                messages_update = output.get("messages")
            elif hasattr(output, "update") and isinstance(output.update, dict):
                 messages_update = output.update.get("messages")
            
            if messages_update:
                # messages_update could be a list or single message
                if not isinstance(messages_update, list):
                    messages_update = [messages_update]
                
                for msg in messages_update:
                     # Check additional_kwargs for sources
                     if hasattr(msg, "additional_kwargs"):
                         sources = msg.additional_kwargs.get("sources")
                         if sources:
                             yield _json_event("sources", content=sources, metadata={"agent_name": name})

            yield _json_event("agent_end", metadata={
                "agent_name": name,
                "agent_id": f"{workflow_id}_{name}_{langgraph_step}"
            })

        # 2. LLM Streaming (Message & Reasoning)
        elif kind == "on_chat_model_stream" and node in streaming_llm_agents:
            chunk = data["chunk"]
            content = chunk.content
            
            # Normalize content
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        text_parts.append(part["text"])
                    elif hasattr(part, "text"):
                        text_parts.append(part.text)
                content = "".join(text_parts)
            
             # A. Reasoning Content (Flash Thinking)
            reasoning = chunk.additional_kwargs.get("reasoning_content")
            if reasoning:
                 yield _json_event("reasoning_delta", content=reasoning, metadata={
                     "agent_name": node,
                     "id": run_id
                 })

            # B. Standard Content
            if content:
                yield _json_event("message_delta", content=content, metadata={
                    "agent_name": node,
                    "id": run_id
                })

        # 3. Tool Events
        elif kind == "on_tool_start" and node in TEAM_MEMBERS:
             yield _json_event("tool_call", content={
                 "tool_name": name,
                 "input": data.get("input")
             }, metadata={"agent_name": node, "run_id": run_id})

        elif kind == "on_tool_end" and node in TEAM_MEMBERS:
            yield _json_event("tool_result", content={
                "tool_name": name,
                "result": data["output"].content if data.get("output") else ""
            }, metadata={"agent_name": node, "run_id": run_id})

        # 4. Custom Events (Phase Change & Progress) [NEW]
        elif kind == "on_custom_event":
            # Check event name to distinguish types
            if name == "phase_change":
                 yield _json_event("phase_change", content=data, metadata={"agent_name": node, "run_id": run_id})
            else:
                 yield _json_event("progress", content=data, metadata={"agent_name": node, "run_id": run_id})

