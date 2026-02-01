# Post-Task Actions

Whenever a task is completed, ensure the following actions are taken:

1. **Linting & Formatting**:
   - Run `black` for Python files.
   - Run `npm run lint` (if available) for Frontend.

2. **Testing**:
   - Run unit tests relevant to the changes (`pytest` or `npm run test`).
   - If UI changes were made, run E2E tests: `npm run test:e2e`.
   - **Important**: Before E2E tests, run `backend/scripts/restart_services.sh`.

3. **Documentation**:
   - Update `README.md` if high-level specifications change.
   - Ensure `project_overview.md` in Serena memories is updated if the tech stack or architecture evolves.

4. **Verification**:
   - Manually verify the changes in the browser if applicable.
