# Style and Conventions

## Backend (Python)
- **Formatter**: `black` (line length 88).
- **Testing**: `pytest` with coverage.
- **Dependency Management**: `uv` / `pip`.
- **Typing**: Strong typing encouraged (Pydantic used heavily for LangGraph state).
- **Structure**: `src/` layout.

## Frontend (TypeScript/React)
- **Framework**: Next.js 15 (App Router likely).
- **Styling**: TailwindCSS (utility-first).
- **Testing**: Vitest for unit, Playwright for E2E.
- **Linting**: ESLint.
- **Conventions**:
  - `src/` directory structure.
  - Component-based architecture.
  - Shadcn/UI (Radix + Tailwind) patterns used.
