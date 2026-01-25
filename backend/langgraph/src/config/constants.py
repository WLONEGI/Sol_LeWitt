"""
Project-wide constants.
"""

from typing import Final

# Retry limits
MAX_RETRIES: Final[int] = 3


# Concurrency limits
VISUALIZER_CONCURRENCY: Final[int] = 5

# Recursion limits
RECURSION_LIMIT_WORKFLOW: Final[int] = 50
RECURSION_LIMIT_RESEARCHER: Final[int] = 7

# Templates
# Note: Using {role} and {content} as keys for format
RESPONSE_FORMAT: Final[str] = "Response from {role}:\n\n<response>\n{content}\n</response>\n\n*Step completed.*"
