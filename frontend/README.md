This is a [Next.js](https://nextjs.org) project bootstrapped with [`create-next-app`](https://nextjs.org/docs/app/api-reference/cli/create-next-app).

## Project Structure

The frontend follows a feature-based organization (inspired by Feature-Sliced Design) to improve maintainability and encapsulation.

```
src/
├── app/                  # Next.js App Router (Routes & Layouts)
├── components/           # Shared UI Components (Generic, non-business)
│   ├── ui/               # Base UI components (Radix/Shadcn)
│   └── layout/           # Shared layout components
├── features/             # Business Domains (Encapsulated)
│   ├── chat/             # Chat domain (Components, Store, Hooks, Types)
│   └── preview/          # Artifact Preview domain (Components, Store, Types)
├── hooks/                # Global/Shared React hooks
├── lib/                  # Shared utility functions and library configs
└── types/                # Global/Shared TypeScript definitions
```

### Key Features
- **chat**: Handles the AI chat interface, message history, and timeline management.
- **preview**: Manages the visualization of generated artifacts (slides, logs, reports).

## Getting Started

First, run the development server:

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

## Development

- **State Management**: Uses [Zustand](https://github.com/pmndrs/zustand) for feature-scoped state.
- **AI Integration**: Uses [Vercel AI SDK](https://sdk.vercel.ai/docs) for streaming chat responses.
- **Styling**: Tailwind CSS and Framer Motion for animations.

## Testing

Run E2E tests with Playwright:

```bash
npm run test:e2e
```
