# Changelog

## Index

- [0.3.0 — Dynamic Model Switching & Nous Direct API](#030--dynamic-model-switching--nous-direct-api)
- [0.2.2 — PYTHONPATH Install Strategy](#022--pythonpath-install-strategy)
- [0.2.1 — Fly.io Deployment Fix](#021--flyio-deployment-fix)
- [0.2.0 — Hermes Agent Integration](#020--hermes-agent-integration)
- [0.1.0 — Project Scaffolding](#010--project-scaffolding)

---

## 0.3.0 — Dynamic Model Switching & Nous Direct API

**2026-03-10**

Added a model selector dropdown to the terminal header so the active LLM can be switched on-the-fly without redeploying. Also added support for the Nous Research inference API as a direct provider alongside OpenRouter, reducing latency by skipping the OpenRouter proxy layer.

### Added

- **Model selector UI** (`frontend/index.html`, `frontend/style.css`) — `<select>` dropdown in the header bar, styled to match the Evangelion aesthetic. Models are grouped by provider using `<optgroup>`.
- **`GET /api/models`** (`server/main.py`) — REST endpoint that returns available providers and their models. Only providers with a configured API key are included, so the dropdown adapts to the deployment's secrets.
- **WebSocket `config` message** (`server/main.py`, `frontend/main.js`) — new message type `{ type: "config", model, provider }` lets the frontend set the model/provider per session. Switching models resets conversation history and lazily recreates the agent on the next chat message.
- **Nous Research direct inference** — support for `HERMES_API_KEY` (from [portal.nousresearch.com](https://portal.nousresearch.com)) hitting `https://inference-api.nousresearch.com/v1` directly, bypassing OpenRouter. Available models: Hermes 3 70B, DeepHermes 3 8B.
- **Multi-provider architecture** (`server/main.py`) — `PROVIDERS` dict maps each provider to its `base_url`, API key env var, and model catalogue. Adding a new provider is a single dict entry.

### Changed

- **`server/main.py`** — `_create_agent()` now accepts `model` and `provider_id` parameters, passing the appropriate `base_url` and `api_key` to `AIAgent`. Agent creation is deferred until the first chat message (lazy init).
- **`frontend/main.js`** — `loadModels()` fetches `/api/models` on page load and populates the dropdown. Model selection is sent as a `config` message on change and on each WebSocket reconnect.
- **`.env.example`** — documented `HERMES_API_KEY` for Nous direct inference.

---

## 0.2.2 — PYTHONPATH Install Strategy

**2026-03-10**

The 0.2.1 `pyproject.toml` patch fixed the missing `agent/` package but exposed a second missing sub-package (`tools/environments/`). Upstream `hermes-agent` also omits `tools.*` sub-packages from its `packages.find.include`, so patching individual entries is a game of whack-a-mole.

### Changed

- **Dockerfile** — replaced the `sed`-patch-then-pip-install approach with a `PYTHONPATH`-based strategy: clone the full `hermes-agent` source to `/opt/hermes-agent`, install only its dependencies via `requirements.txt`, and set `PYTHONPATH` so Python resolves all imports directly from the source tree. This sidesteps all upstream packaging omissions at once.

### Fixed

- **`ModuleNotFoundError: No module named 'tools.environments'`** — `tools/terminal_tool.py` imports `tools.environments.singularity`, a sub-package not included in the upstream package build.

---

## 0.2.1 — Fly.io Deployment Fix

**2026-03-10**

Fixed deployment to Fly.io under the `crimson-sun-technologies` org. The app crashed on first connect due to a missing `agent` module in the upstream `hermes-agent` package.

### Changed

- **`fly.toml`** — switched primary region from `ams` to `sin` (Singapore).
- **Dockerfile** — clones `hermes-agent` from source and patches `pyproject.toml` to include the missing `agent/` package before installing. Upstream omits it from `packages.find`.
- **`server/requirements.txt`** — removed `hermes-agent` (now installed via Dockerfile clone step); dropped `[all]` extras that pulled unnecessary dependencies and caused build timeouts.

### Fixed

- **`ModuleNotFoundError: No module named 'agent'`** — the upstream `hermes-agent` `pyproject.toml` doesn't list the `agent/` directory in its package includes, so `tools/web_tools.py` fails to import `agent.auxiliary_client` at runtime.

---

## 0.2.0 — Hermes Agent Integration

**2026-03-09**

Replaced the echo stub with a live Hermes agent session. See [`0.2.0-agent-integration.md`](0.2.0-agent-integration.md) for full implementation notes.

### Added

- **Hermes agent integration** (`server/main.py`) — each WebSocket connection gets its own `AIAgent` instance with multi-turn conversation support via `run_conversation()`.
- **Environment loading** — `python-dotenv` reads `.env` at startup; `OPENROUTER_API_KEY` is now actually consumed.
- **Processing indicator** (`frontend/main.js`, `frontend/style.css`) — pulsing "PROCESSING..." message while the agent thinks, input disabled during this state.
- **Configurable model** — `LLM_MODEL` and `HERMES_MAX_ITERATIONS` env vars control agent behavior.

### Changed

- **Dockerfile** — installs `git` for pip to clone `hermes-agent` from GitHub.
- **`server/requirements.txt`** — added `python-dotenv` and `hermes-agent[all]`.
- **`.env.example`** — added Hermes-specific config options.

### Security

- Terminal/shell toolset disabled (`disabled_toolsets=["terminal"]`) to prevent the agent from running arbitrary commands on the server.

---

## 0.1.0 — Project Scaffolding

**2026-03-09**

Initial project scaffold for self-hosting the [Hermes agent](https://hermes-agent.nousresearch.com/) on Fly.io with an Evangelion-inspired terminal web UI.

### Added

- **FastAPI server** (`server/main.py`) — serves the frontend and exposes a WebSocket endpoint at `/ws` for real-time agent communication. Currently echoes input back as a stub.
- **Terminal UI** (`frontend/`) — single-page vanilla HTML/CSS/JS interface with:
  - Scanline overlay, neon red/blue/green palette, dark panel backgrounds
  - WebSocket client with auto-reconnect
  - Status indicator, sync ratio display, message history
- **Dockerfile** — Python 3.11-slim container serving the full app via uvicorn on port 8080.
- **fly.toml** — Fly.io deployment config targeting Amsterdam (`ams`), with auto-stop/start for cost efficiency.
- **docker-compose.yml** — local dev environment with hot-reload volume mounts.
- **Makefile** — shortcuts for `dev`, `up`, `down`, `deploy`, `logs`, `ssh`, `status`.
- **`.env.example`** — template for required API keys (OpenRouter, etc.).
- **`.gitignore` / `.dockerignore`** — standard exclusions for Python, Docker, IDE files.

### Architecture Decision

Chose **FastAPI + vanilla frontend** over Vue/Vite + Node for simplicity: one process, one port, no build step, no `node_modules`. The UI is a terminal emulator — a single WebSocket connection and ~200 lines of JS. Frameworks can be introduced later if complexity warrants it.
