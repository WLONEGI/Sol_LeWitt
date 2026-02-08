# Architecture Map & Symbol Analysis

## Architecture Map

### Backend (`/backend/src`)
- **`core/workflow`**: The heart of the application. Implements a Multi-Agent System using **LangGraph**.
    - **`builder.py`**: Defines the `StateGraph`. Components: `coordinator`, `planner`, `supervisor`, `researcher`, `writer`, `visualizer`, `data_analyst`.
    - **`state.py`**: Defines the shared state (`State` class) containing the execution plan (`TaskStep`), artifacts, and conversation history.
    - **`nodes/`**: Implementation of individual agents/nodes. `visualizer.py` seems to be the largest, suggesting complex logic for image generation/handling.
- **`app`**: API Layer (FastAPI).
- **`infrastructure`**: (Inferred) Integration with Vertex AI, Gemini, Cloud Storage, and PostgreSQL.

### Frontend (`/frontend/src`)
- **`features/chat`**: Main user interface module.
    - **`components/`**: React components for the chat view.
    - **`hooks/`**: Custom hooks (e.g., for handling streams).
    - **`stores/`**: State management (likely Zustand).
    - **`types/`**: TypeScript definitions for chat entities.
- **`app/`**: Next.js App Router pages. `layout.tsx` sets up providers.

## Symbol Analysis: Execution Flow

1.  **Entry Point (Backend)**:
    - `backend/main.py`: `run_agent_workflow(user_input)`
    - Calls `graph.ainvoke(...)` with the user input.

2.  **Graph Execution (`src.core.workflow.builder`)**:
    - **Start** -> `coordinator`: Analyzes user intent.
    - `plan_manager` / `planner`: Creates or updates the execution plan (`State.plan`).
    - `supervisor`: Orchestrates execution, delegating tasks to workers based on the plan.
    - **Workers**:
        - `researcher`: Subgraph for gathering information.
        - `writer`: Drafts content.
        - `visualizer`: Generates images/slides.
        - `data_analyst`: Processes data.
    - **Loop**: Workers return results -> `supervisor` updates state -> Checks if more steps are needed.

3.  **Data Flow**:
    - `State` object flows between nodes.
    - Key data: `messages` (chat history), `plan` (list of steps), `artifacts` (generated content).

## Dependencies
- **LangGraph**: Orchestration.
- **Vertex AI / Gemini**: LLM intelligence.
- **PostgreSQL**: State persistence (checkpointer).
