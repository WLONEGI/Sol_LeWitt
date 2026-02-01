# Project Overview: AI Slide with Nano Banana

## Purpose
An AI-powered slide generation system that produces high-quality, full-page slide images from text input, logos, and design reference PPTX files. It leverages multi-agent collaboration via LangGraph to research, plan, write, and visualize slides.

## Tech Stack
- **Frontend**: Next.js 16 (App Router), TypeScript, Tailwind CSS 4, Radix UI, Framer Motion, Vercel AI SDK (Data Stream Protocol v1), Zustand.
- **Backend**: Python 3.12+, FastAPI, LangGraph, LangChain, Google GenAI SDK (Gemini).
- **AI Models**: 
  - Reasoning/Logic: `gemini-3-flash-preview`
  - Vision/Imaging: `gemini-3-pro-image-preview` (Nano Banana Pro)
  - High Reasoning: `gemini-3-pro-preview`
- **Infrastructure**: Vertex AI, GCP Cloud SQL (PostgreSQL) with `cloud-sql-proxy`.

## Core Architecture
- **Multi-Agent (LangGraph)**: Coordinator -> Planner -> Supervisor -> Workers (Researcher, Data Analyst, Storywriter, Visualizer, Coder).
- **Dual-Pane UI**: Interactive Chat on the left, Live Preview on the right.
- **Data Stream Protocol**: Uses Vercel AI SDK's SSE protocol for real-time updates of text, reasoning, and UI steps.
