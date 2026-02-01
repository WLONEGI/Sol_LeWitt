import logging
from src.shared.config.settings import settings

# Try importing Postgres dependencies
try:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg_pool import AsyncConnectionPool
    HAS_POSTGRES_DEPS = True
except ImportError:
    HAS_POSTGRES_DEPS = False

from src.core.workflow import build_graph


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
            # [Fix] Patch psycopg to handle LangChain objects in JSONB columns
            from langchain_core.load import dumps as lc_dumps
            from psycopg.types.json import set_json_dumps
            
            def custom_json_dumps(obj):
                return lc_dumps(obj)

            set_json_dumps(custom_json_dumps)
            logger.info("✅ Configured psycopg to use langchain_core.load.dumps.")

            # Create connection pool
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


# Expose singleton instance for module-level access
_manager = WorkflowManager()


async def initialize_graph():
    """Initialize the workflow graph. Called at app startup."""
    await _manager.initialize()


async def close_graph():
    """Close the workflow graph resources. Called at app shutdown."""
    await _manager.close()
