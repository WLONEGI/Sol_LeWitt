# Project Overview

**Project Name**: AI Slide Generator (Visual Blueprinting phase)

## Purpose
Automated generation of presentation slides (PDF) from text, logos, and design templates using Generative AI (Nano Banana Pro for visuals, Gemini 2.5/3.0 for logic).

## Architecture
- **Monorepo Structure**:
  - `backend/`: Python (FastAPI, LangChain, LangGraph, Vertex AI). Focus on "Visual Blueprinting" and "Deep Edit".
  - `frontend/`: TypeScript (Next.js 15, React 18). Dual-pane interface (Chat + Preview).

## Key Features
- **Input**: Text, Logo, PPTX.
- **Output**: Full-image PDF slides.
- **Workflow**: Plan-Driven (Coordinator -> Planner -> Researcher -> Data Analyst -> Visualizer).
- **UX**: Dual-Pane Workspace, Chat-driven interaction.

## Tech Stack
- **Backend**: Python 3.12+, FastAPI, LangGraph, Google Vertex AI (Gemini), PostgreSQL (Cloud SQL).
- **Frontend**: Next.js 15, React 18, TailwindCSS, Radix UI, Zustand, Playwright.
