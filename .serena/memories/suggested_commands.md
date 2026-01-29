# Suggested Commands

## Backend (Python)
- **Install Dependencies**: 
  - Using `uv`: `cd backend && uv sync`
  - Using `pip`: `cd backend && pip install -r requirements.txt` (or `-e .`)
- **Run Server**: `cd backend && python main.py` (Assuming main.py is entry point, check file for details)
- **Run Tests**: `cd backend && pytest`
- **Formatting**: `black .`

## Frontend (Next.js)
- **Install Dependencies**: `cd frontend && npm install`
- **Run Development Server**: `cd frontend && npm run dev`
- **Run Unit Tests**: `cd frontend && npm test` (`vitest`)
- **Run E2E Tests**: `cd frontend && npm run test:e2e` (`playwright`)
- **Linting**: `cd frontend && npx eslint .`
