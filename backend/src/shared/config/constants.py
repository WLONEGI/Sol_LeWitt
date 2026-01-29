
# Define the team members (Worker nodes) in the graph
TEAM_MEMBERS = [
    "researcher",
    "planner",
    "storywriter",
    "visualizer",
    "data_analyst",
]

# Mapping of agents to their preferred LLM type
AGENT_LLM_MAP = {
    "coordinator": "basic",
    "planner": "high_reasoning",
    "researcher": "reasoning",
    "storywriter": "high_reasoning",
    "visualizer": "basic",
    "data_analyst": "reasoning",
}
