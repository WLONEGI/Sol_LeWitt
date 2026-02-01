# Suggested Commands

## General
- View project structure: `ls -R` or `tree`
- Search codebase: `grep -r "pattern" .`

## Backend (FastAPI / LangGraph)
- **Start Server**: `python backend/server.py` (Local entry point)
- **Install Dependencies**: `cd backend && pip install -r requirements.txt` (or use `uv` if preferred by user)
- **Run Tests**: `cd backend && pytest`
- **Restart Services**: `backend/scripts/restart_services.sh` (Stops existing processes and restarts)

## Frontend (Next.js)
- **Start Development Server**: `cd frontend && npm run dev`
- **Build**: `cd frontend && npm run build`
- **Unit Tests**: `cd frontend && npm run test`
- **E2E Tests (Playwright)**: `cd frontend && npm run test:e2e`

## Infrastructure
- **Cloud SQL Proxy**: Start `cloud-sql-proxy` before connecting to the database.
