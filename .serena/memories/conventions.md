# Coding Conventions and Rules

## AI Model Usage (Strict)
Always use the following model IDs for specific tasks. Do NOT use `gemini-1.5` or other older IDs.
- **Reasoning**: `gemini-3-flash-preview` (Planner, Researcher)
- **Basic**: `gemini-3-flash-preview` (Coordinator)
- **Vision**: `gemini-3-pro-image-preview` (Visualizer, Image generation)
- **High Reasoning**: `gemini-3-pro-preview` (Complex logic, Code generation)

## Architecture Guidelines
- **LangGraph**: Always follow the Plan-Driven Architecture.
- **Data Stream Protocol**: Follow Vercel AI SDK Data Stream Protocol (v1). Use `data-` prefix for custom UI updates (e.g., `data-ui_step_update`).
- **Database**: Must use `cloud-sql-proxy` for connections. No direct public IP access.

## Coding Style
- **Python**: Use `black` for formatting. Follow typing hints and standard docstring formats.
- **TypeScript**: Use functional components, hooks, and clean architecture. Prefer Tailwind CSS for styling.
- **Tests**: Create verification scripts in the `test` folder of each module.
