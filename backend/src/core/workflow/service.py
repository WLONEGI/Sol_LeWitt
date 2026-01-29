import logging
import uuid
import json
from typing import Any, AsyncGenerator
# from langchain_community.adapters.openai import convert_message_to_dict
# from langgraph.checkpoint.memory import MemorySaver

from src.shared.config import TEAM_MEMBERS
from src.shared.config.settings import settings
from src.core.workflow import build_graph

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
            # [Fix] Patch psycopg to use JsonPlusSerializer for JSONB columns
            # This is required because LangGraph's Send objects are not standard JSON serializable,
            # and AsyncPostgresSaver (v3) might rely on psycopg to serialize dicts for JSONB columns.
            from langgraph.checkpoint.serde.jsonplus import _msgpack_ext_hook_to_json
            from psycopg.types.json import set_json_dumps
            import json

            def custom_json_dumps(obj):
                return json.dumps(obj, default=_msgpack_ext_hook_to_json, ensure_ascii=False)

            set_json_dumps(custom_json_dumps)
            logger.info("✅ Configured psycopg to use JsonPlusSerializer.")

            # Create connection pool
            # Use settings.connection_string which handles Cloud Run Unix Socket logic
            connection_info = settings.connection_string
            
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
            from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
            checkpointer = AsyncPostgresSaver(self.pool, serde=JsonPlusSerializer())
            await checkpointer.setup()
            
            # Build graph
            self.graph = build_graph(checkpointer=checkpointer)
            logger.info("✅ Graph initialized with AsyncPostgresSaver (JsonPlusSerializer). Persistence enabled.")
            
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

    streaming_llm_agents = [*TEAM_MEMBERS, "planner", "coordinator", "supervisor"]

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
        metadata = event.get("metadata", {})
        
        # DEBUG LOGGING KEPT FOR DIAGNOSIS
        logger.info(f"[DEBUG_STREAM] Event: kind={kind}, name={name}, agent={metadata.get('agent_name')}, node={metadata.get('checkpoint_ns')}")
        
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
        
        # --- 1. Agent Start/End Events & Artifact Lifecycle ---
        
        # [A] Artifact Open (Pseudo-Tool Start)
        # When specific workers start, notify UI to show skeleton loader
        if kind == "on_chain_start" and name in ["storywriter", "visualizer", "data_analyst"]:
             # Determine artifact kind based on node name
            art_kind = "document"
            title = "Working..."
            if name == "storywriter":
                art_kind = "document"
                title = "ドキュメントを作成中..."
            elif name == "visualizer":
                art_kind = "image"
                title = "画像を生成中..."
            elif name == "data_analyst":
                art_kind = "code_analysis"
                title = "コードを実行中..."

            yield _json_event("artifact_open", content={
                "artifactId": f"{workflow_id}_{name}_{langgraph_step}",
                "kind": art_kind,
                "title": title
            }, metadata={"agent_name": name})

        # [B] Agent/Workflow Start
        if kind == "on_chain_start" and name in streaming_llm_agents:
            if name == "planner":
                # Special event for workflow start
                yield _json_event("workflow_start", metadata={
                    "workflow_id": workflow_id,
                    "thread_id": thread_id
                })
            
            yield _json_event("agent_start", metadata={
                "name": name,
                "agent_name": name,
                "agent_id": f"{workflow_id}_{name}_{langgraph_step}"
            })

        # [C] Agent End & Artifact Ready / Plan Update
        elif kind == "on_chain_end" and name in streaming_llm_agents:
            output = data.get("output")
            
            # --- Handle Plan Update (Planner) ---
            if name in ["planner", "supervisor"]:
                # Check if output contains a plan
                # Output might be a dict or Command object
                plan_data = None
                if isinstance(output, dict):
                    plan_data = output.get("plan")
                elif hasattr(output, "update") and isinstance(output.update, dict):
                    plan_data = output.update.get("plan")
                elif hasattr(output, "plan"): # Pydantic model
                    plan_data = output.plan

                if plan_data:
                     yield _json_event("plan_update", content={
                         "plan": plan_data
                     }, metadata={"agent_name": name})

            # --- Handle Artifact Ready (Workers) ---
            # Check for 'artifacts' in output
            artifact_update = None
            if isinstance(output, dict): 
                 artifact_update = output.get("artifacts")
            elif hasattr(output, "update"):
                 artifact_update = output.update.get("artifacts") if isinstance(output.update, dict) else None

            if artifact_update:
                for key, content in artifact_update.items():
                    # Determine Artifact Type
                    art_kind = "document" # default
                    if "_visual" in key: art_kind = "image"
                    elif "_data" in key: art_kind = "code_analysis"
                    
                    artifact_id = f"{workflow_id}_{name}_{langgraph_step}" # Must match artifact_open ID
                    
                    # For image, content might be prompt or URL depending on impl.
                    # Assuming implementation returns URL or we handle it here.
                    # As per Vercel spec, we need 'payload'
                    
                    payload = {}
                    if art_kind == "document":
                        payload = {"kind": "document", "content": content, "format": "markdown"}
                    elif art_kind == "image":
                         # Assuming content is the URL or we wrap it
                        payload = {"kind": "image", "url": content, "prompt": "Generated Image"}
                    elif art_kind == "code_analysis":
                        payload = {"kind": "code_analysis", "code": content, "result": ""}

                    yield _json_event("artifact_ready", content={
                        "artifactId": artifact_id,
                        "payload": payload
                    }, metadata={"agent_name": name})

            # --- Handle Slide Outline Special Event (Storywriter) ---
            if name == "storywriter":
                slides = None
                if isinstance(output, dict):
                    slides = output.get("slides")
                elif hasattr(output, "update") and isinstance(output.update, dict):
                    slides = output.update.get("slides")
                elif hasattr(output, "slides"):
                    slides = output.slides
                
                if slides:
                    # Convert to list of dicts if it's Pydantic models
                    if not isinstance(slides, list): slides = []
                    serializable_slides = [
                        s.model_dump() if hasattr(s, "model_dump") else s 
                        for s in slides
                    ]
                    yield _json_event("slide_outline", content={
                        "slides": serializable_slides
                    }, metadata={"agent_name": name})

            # --- Handle Sources ---
            messages_update = None
            if isinstance(output, dict):
                messages_update = output.get("messages")
            elif hasattr(output, "update") and isinstance(output.update, dict):
                 messages_update = output.update.get("messages")
            
            if messages_update:
                if not isinstance(messages_update, list): messages_update = [messages_update]
                for msg in messages_update:
                     # 1. Extract Sources
                     sources = None
                     if hasattr(msg, "additional_kwargs"):
                         sources = msg.additional_kwargs.get("sources")
                     elif isinstance(msg, dict):
                         # In serialized events, properties might be dict keys
                         sources = msg.get("additional_kwargs", {}).get("sources")
                     
                     if sources:
                         yield _json_event("sources", content=sources, metadata={"agent_name": name})

                     # 2. Extract Content for Coordinator (Structured Output fallback)
                     content = None
                     if hasattr(msg, "content"):
                         content = msg.content
                     elif isinstance(msg, dict):
                         content = msg.get("content")

                     if name in ["coordinator", "supervisor"] and content:
                         # We send it as a 'message_delta' containing the full response.
                         yield _json_event("message_delta", content=content, metadata={
                             "agent_name": name,
                             "id": run_id or f"msg_{uuid.uuid4().hex[:8]}"
                         })

            yield _json_event("agent_end", metadata={
                "agent_name": name,
                "agent_id": f"{workflow_id}_{name}_{langgraph_step}"
            })

        # --- 2. LLM Streaming (Message & Reasoning) ---
        elif kind == "on_chat_model_stream":
             # "node" might be empty for some internal chains, relying on name/metadata
            agent_name = node if node else name
            
            # Maintain a set of active reasoning run_ids in the generator closure
            if not hasattr(run_agent_workflow, "active_reasoning_ids"):
                run_agent_workflow.active_reasoning_ids = set()

            if agent_name in streaming_llm_agents or True: # Allow all models to stream for now
                chunk = data["chunk"]
                content = chunk.content
                logger.info(f"[DEBUG_STREAM] on_chat_model_stream content: {content!r} for agent: {agent_name}")
                
                # Normalize content
                if isinstance(content, list):
                    text_parts = []
                    for part in content:
                        if isinstance(part, dict) and "text" in part:
                            text_parts.append(part["text"])
                        elif hasattr(part, "text"):
                            text_parts.append(part.text)
                    content = "".join(text_parts)
                
                # A. Reasoning Content (Think Block)
                # Only if strictly available in additional_kwargs (Gemini/DeepSeek style)
                reasoning = chunk.additional_kwargs.get("reasoning_content")
                if reasoning:
                        # [Start Event] If this run_id hasn't started reasoning yet
                        if run_id not in run_agent_workflow.active_reasoning_ids:
                             run_agent_workflow.active_reasoning_ids.add(run_id)
                             yield _json_event("reasoning-start", content="", metadata={
                                "agent_name": agent_name,
                                "id": run_id
                            })

                        # [Delta Event]
                        yield _json_event("reasoning-delta", content=reasoning, metadata={
                            "agent_name": agent_name,
                            "id": run_id
                        })

                # B. Standard Content
                if content:
                    # [End Event] If we received content and were in reasoning mode, close it
                    if run_id in run_agent_workflow.active_reasoning_ids:
                         run_agent_workflow.active_reasoning_ids.remove(run_id)
                         yield _json_event("reasoning-end", content="", metadata={
                            "agent_name": agent_name,
                            "id": run_id
                        })

                    yield _json_event("message_delta", content=content, metadata={
                        "agent_name": agent_name,
                        "id": run_id
                    })

        # --- 2.5 LLM End Event (Ensure Reasoning Closed) ---
        elif kind == "on_chat_model_end":
             if not hasattr(run_agent_workflow, "active_reasoning_ids"):
                run_agent_workflow.active_reasoning_ids = set()
             
             if run_id in run_agent_workflow.active_reasoning_ids:
                 run_agent_workflow.active_reasoning_ids.remove(run_id)
                 yield _json_event("reasoning-end", content="", metadata={
                    "agent_name": node if node else name,
                    "id": run_id
                })

        # --- 3. Tool Events ---
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

        # --- 4. Custom Events (Progress & Thought) ---
        elif kind == "on_custom_event":
            # Stream of Thought
            if name == "thought":
                # content is {"token": "..."}
                yield _json_event("thought", content=data, metadata={"agent_name": node, "run_id": run_id})

            # For Researcher standard updates or generic progress
            elif name == "progress": # Assuming internal convention
                 yield _json_event("progress", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "visualizer_progress":
                 # [NEW] Visualizer Streaming
                 yield _json_event("data-visualizer-progress", content=data, metadata={"agent_name": node, "run_id": run_id})



            elif name == "title_generated":
                # [NEW] Session Title Generated
                yield _json_event("data-title-generated", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "message_delta":
                # [NEW] Manual streaming from nodes (bypass standard model events)
                logger.info(f"[DEBUG_STREAM] Processing custom event 'message_delta': {data!r}")
                yield _json_event("message_delta", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "storywriter-partial-json":
                # [NEW] Storywriter partial JSON streaming
                # data contains {"args": "...", "delta": "..."}
                yield _json_event("data-storywriter-partial", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "planner-partial-json":
                # [NEW] Planner partial JSON streaming
                yield _json_event("data-planner-partial", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "research-worker-start":
                yield _json_event("data-research-worker-start", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "research-worker-delta":
                yield _json_event("data-research-worker-delta", content=data, metadata={"agent_name": node, "run_id": run_id})

            elif name == "research-worker-end":
                yield _json_event("data-research-worker-end", content=data, metadata={"agent_name": node, "run_id": run_id})

