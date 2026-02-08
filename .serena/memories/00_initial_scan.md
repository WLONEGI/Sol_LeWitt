# Project Initial Scan

## Overview
- **Project Name**: AI_Slide_with_nano_banana (inferred from path)
- **Backend**: Python (FastAPI, LangChain, LangGraph)
- **Frontend**: TypeScript (Next.js 16, React 19, Tailwind CSS)
- **Database**: PostgreSQL (implied by `psycopg` and `init_db.py`)
- **AI/ML**: Google Vertex AI, Gemini

## Directory Structure
### Backend (`/backend`)
- **Dependency Management**: `pyproject.toml`, `requirements.txt`
- **Entry Point**: `main.py` (defines `run_agent_workflow`)
- **Source (`src/`)**:
  - `core/`: Core business logic and workflow definitions.
  - `domain/`: Domain models and interfaces.
  - `infrastructure/`: External services (LLM, DB).
  - `app/`: API routes/controllers.
  - `shared/`: Shared utilities.

### Frontend (`/frontend`)
- **Framework**: Next.js (App Router)
- **Source (`src/`)**:
  - `app/`: Pages and layouts.
  - `features/`: Feature-based modules.
  - `components/`: Reusable UI components.
  - `ai/`: AI integration (Vercel AI SDK?).
  - `providers/`: Context providers (Auth, Theme).

## Key Observations
- The backend appears to use **LangGraph** for agentic workflows (`run_agent_workflow` calls `graph.ainvoke`).
- The frontend uses **Vercel AI SDK** (`ai`, `@ai-sdk/react`) for streaming chat interfaces.
- Authentication seems to use **Firebase** (`firebase-admin` in backend, `firebase` in frontend).
