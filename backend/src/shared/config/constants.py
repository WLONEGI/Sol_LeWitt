
# Define the team members (Worker nodes) in the graph
TEAM_MEMBERS = [
    "researcher",
    "planner",
    "writer",
    "visualizer",
    "data_analyst",
]

# Mapping of agents to their preferred LLM type
AGENT_LLM_MAP = {
    "coordinator": "basic",
    "planner": "high_reasoning",
    "researcher": "reasoning",
    "writer": "high_reasoning",
    "visualizer": "basic",
    "data_analyst": "reasoning",
}
