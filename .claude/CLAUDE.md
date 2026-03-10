# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hermes is a self-hosted web terminal for interacting with the Hermes AI agent (from Nous Research). It wraps the agent in an Evangelion-inspired retrofuturist UI — dark backgrounds, neon accents, scanline overlays, dense monospace layout. Deployed on Fly.io.

## Commands

```bash
make dev          # Run locally with hot-reload (uvicorn, port 8080)
make up           # Run via Docker Compose (port 8080)
make down         # Stop Docker Compose
make deploy       # Deploy to Fly.io
make logs         # Tail Fly.io logs
make ssh          # SSH into Fly.io machine
make status       # Fly.io app status
```

## Architecture

- **`server/main.py`** — FastAPI app. Serves the frontend as static files and exposes a `/ws` WebSocket endpoint for real-time chat. The WebSocket handler is where the Hermes agent integration goes (currently echoes input).
- **`frontend/`** — Vanilla HTML/CSS/JS (no build step). Connects to `/ws` on load, auto-reconnects on disconnect. Static assets served from `/static` via FastAPI's `StaticFiles` mount.
- Communication is exclusively via WebSocket JSON messages with shape `{ type: "system"|"user"|"assistant", content: string }`.

### Hermes Agent Dependency

The upstream `hermes-agent` repo (`NousResearch/hermes-agent`) has a broken `pyproject.toml` that omits several sub-packages (`agent/`, `tools/environments/`). Because of this, the Dockerfile clones the repo into `/opt/hermes-agent` and adds it to `PYTHONPATH` instead of pip-installing it. The agent's own `requirements.txt` is installed separately. This means:

- `from run_agent import AIAgent` works only because `PYTHONPATH` includes the cloned source root.
- For local dev without Docker, you must clone `hermes-agent` yourself and set `PYTHONPATH` to include it.
- `AIAgent.run_conversation()` is synchronous — it's wrapped in `loop.run_in_executor()` to avoid blocking the event loop.

### Agent Configuration

Controlled via env vars: `LLM_MODEL` (default: `nousresearch/hermes-3-llama-3.1-405b`), `HERMES_MAX_ITERATIONS` (default: `10`). The `terminal` toolset is disabled for safety.

## Design Language

The UI follows an Evangelion/NERV-inspired aesthetic: CRT scanlines, neon red/blue/green/amber palette, monospace typography, information-dense layout. See `docs/ui-guidelines.md` for full design guidelines. Preserve this aesthetic when adding UI elements.

## Environment

Copy `.env.example` to `.env`. Requires at minimum `OPENROUTER_API_KEY`. Optional keys: `FIRECRAWL_API_KEY` (web tools), `FAL_KEY` (image generation), `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` (bypass OpenRouter). The app runs on port 8080 in all environments.
