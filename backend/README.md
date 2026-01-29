# Spell Backend

AI Slide generator backend powered by LangGraph and Gemini.

## Architecture

This project follows a layered architecture to ensure maintainability and testability.

### Directory Structure

```text
backend/
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── main.py              # CLI Entrypoint
├── server.py            # API Entrypoint
├── src/
│   ├── app/             # API Layer (FastAPI)
│   │   ├── app.py       # FastAPI initialization
│   │   └── routers/     # API routes
│   ├── core/            # Application Orchestration
│   │   └── workflow/    # LangGraph definition
│   │       ├── builder.py
│   │       ├── nodes/   # Node implementations
│   │       └── state.py # Graph state definition
│   ├── domain/          # Business Logic (Domain Modules)
│   │   ├── researcher/  # Web search & Information extraction
│   │   ├── designer/    # Image generation & Visual assets
│   │   ├── writer/      # Content drafting (Storywriter)
│   │   └── renderer/    # PPTX generation & Template analysis
│   ├── infrastructure/  # External Integrations
│   │   ├── database/    # Persistence & Checkpointing
│   │   ├── storage/     # GCS storage client
│   │   └── llm/         # LLM client factory
│   ├── shared/          # Shared Components
│   │   ├── schemas/     # Pydantic models (IO/Design)
│   │   ├── config/      # Settings & Constants
│   │   └── utils/       # Common utilities (SSE, etc.)
│   └── resources/       # Static assets
│       └── prompts/     # Prompt templates (Markdown)
└── tests/               # Test suite
```

## Getting Started

### Prerequisites
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (Recommended)

### Setup
1. Install dependencies:
   ```bash
   uv sync
   ```
2. Configure environment variables in `.env`.

### Running the Server
```bash
uv run uvicorn server:app --reload --port 8000
```

### Running the CLI
```bash
uv run python main.py
```

## Tech Stack
- **Framework**: FastAPI, LangGraph
- **LLM**: Gemini (Vertex AI)
- **Database**: PostgreSQL (Checkpointing)
- **Storage**: Google Cloud Storage
- **Package Manager**: uv
