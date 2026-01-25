import logging
from typing import Any

from src.config import TEAM_MEMBERS
from src.graph import build_graph

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def enable_debug_logging():
    """Enable debug level logging for more detailed execution information."""
    logging.getLogger("src").setLevel(logging.DEBUG)


# Create the graph
graph = build_graph()


def run_agent_workflow(user_input: str, debug: bool = False) -> dict[str, Any]:
    """Run the agent workflow with the given user input.

    Args:
        user_input: The user's query or request
        debug: If True, enables debug level logging

    Returns:
        The final state after the workflow completes
    """
    import asyncio
    return asyncio.run(run_agent_workflow_async(user_input, debug))


async def run_agent_workflow_async(user_input: str, debug: bool = False) -> dict[str, Any]:
    """Async version of run_agent_workflow. Required because supervisor_node is async."""
    if not user_input:
        raise ValueError("Input could not be empty")

    if debug:
        enable_debug_logging()

    logger.info(f"Starting workflow with user input: {user_input}")
    result = await graph.ainvoke(
        {
            # Runtime Variables
            "messages": [{"role": "user", "content": user_input}],
        },
        {"recursion_limit": 50}
    )
    logger.debug(f"Final workflow state: {result}")
    logger.info("Workflow completed successfully")
    return result


if __name__ == "__main__":
    print(graph.get_graph().draw_mermaid())
