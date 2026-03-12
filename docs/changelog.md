# Changelog

## Index

- [2.1.0 — Vendored Agent Source](#210--vendored-agent-source)
- [2.0.0 — Dead Code Removal & Repo Rename](#200--dead-code-removal--repo-rename)
- [1.0.0 — Hermes Agent Gateway](#100--hermes-agent-gateway)
- [0.4.1 — Agent Timeout Guard](#041--agent-timeout-guard)
- [0.4.0 — Frontend Overhaul](#040--frontend-overhaul)
- [0.3.1 — Model Dropdown Loading Fix](#031--model-dropdown-loading-fix)
- [0.3.0 — Dynamic Model Switching & Nous Direct API](#030--dynamic-model-switching--nous-direct-api)
- [0.2.2 — PYTHONPATH Install Strategy](#022--pythonpath-install-strategy)
- [0.2.1 — Fly.io Deployment Fix](#021--flyio-deployment-fix)
- [0.2.0 — Hermes Agent Integration](#020--hermes-agent-integration)
- [0.1.0 — Project Scaffolding](#010--project-scaffolding)

---

## 2.1.0 — Vendored Agent Source

**2026-03-12**

The Hermes agent was previously installed at Docker build time by cloning the upstream `NousResearch/hermes-agent` GitHub repo. This made the agent's internals read-only — any customisation (memory backends, tool policies, prompt rewrites) required maintaining a separate fork. This release vendors the full agent source into the repository, unlocking direct source-level modification. The immediate motivation is integrating the Elephantasm framework for long-term agentic memory, which requires changes to the agent's core reasoning loop that are impossible through configuration alone.

### Added

- **`hermes-agent/`** — vendored copy of the full [hermes-agent](https://github.com/NousResearch/hermes-agent) source tree, checked into the repository. Contains the CLI entry point (`cli.py`), agent core (`agent/`), tool implementations (`tools/`), and `pyproject.toml` for editable installation. This is the codebase that will be modified for Elephantasm integration.

### Changed

- **`gateway/Dockerfile`** — replaced `git clone --depth 1 https://github.com/NousResearch/hermes-agent.git` with `COPY hermes-agent/ /opt/hermes-agent/`. The agent is now built from the local vendored source rather than fetched from GitHub at build time. `git` remains in the system deps as a transitive build requirement. All `COPY` paths updated to be relative to the new repo-root build context (`gateway/app.py`, `gateway/static/`, `gateway/entrypoint.sh`).
- **`gateway/docker-compose.yml`** — build context widened from `.` (gateway only) to `..` (repo root), with `dockerfile: gateway/Dockerfile`. Required because the Docker build now needs to reach both `hermes-agent/` and `gateway/` from the same context.
- **`gateway/fly.toml`** — `dockerfile` path changed from `Dockerfile` to `gateway/Dockerfile` to match the repo-root build context used by `fly deploy`.
- **`Makefile`** — `deploy` target changed from `cd gateway && fly deploy` to `fly deploy --config gateway/fly.toml`, running from the repo root so the build context includes `hermes-agent/`.

### Architecture

The Docker build context is now the repository root rather than the `gateway/` subdirectory. This is the key structural change — Docker's `COPY` instruction can only reference files within the build context, so including both `hermes-agent/` (agent source) and `gateway/` (web app) requires a context that encompasses both. The `pip install -e ".[all]"` editable install is preserved, meaning `/opt/hermes-agent/` inside the container is both the install target and the live source tree.

This sets the stage for Elephantasm integration: the agent's memory subsystem, tool dispatch, and conversation lifecycle are now directly editable in `hermes-agent/` and version-controlled alongside the gateway.

---

## 2.0.0 — Dead Code Removal & Repo Rename

**2026-03-12**

The gateway app (1.0.0) fully replaced the custom web terminal as the sole deployed app on Fly.io. The custom frontend, FastAPI server, and root deployment config were never deployed again after the gateway went live — making them dead code. This release removes all of it and renames the repository from `hermes` to `hermes-alpha`.

### Removed

- **`frontend/`** — the entire custom Evangelion-themed web UI: 7 ES modules (`js/`), 9 CSS files (`css/`), `index.html`, and `style.css`. Superseded by the stock Hermes CLI rendered via xterm.js in `gateway/`.
- **`server/`** — the custom FastAPI WebSocket server (`main.py`, `requirements.txt`) that wrapped `AIAgent.run_conversation()` with multi-provider routing, model switching, conversation history, and timeout handling. Superseded by the gateway's PTY bridge which runs the stock CLI directly.
- **Root `Dockerfile`** — built the custom frontend app image. The gateway has its own Dockerfile at `gateway/Dockerfile`.
- **Root `fly.toml`** — deployed the custom frontend app. The gateway has its own at `gateway/fly.toml`.
- **Root `docker-compose.yml`** — ran the custom frontend locally. The gateway has its own at `gateway/docker-compose.yml`.

### Changed

- **Repository renamed** — `hejijunhao/hermes` → `hejijunhao/hermes-alpha`. GitHub redirects from the old URL remain active.
- **`Makefile`** — removed stale targets (`dev`, old `deploy`, old `up`/`down`) that referenced deleted files. Promoted gateway targets to top-level: `make deploy` now runs `cd gateway && fly deploy`, `make up`/`down` use `gateway/docker-compose.yml`, etc. The `gateway-` prefix is no longer needed.
- **`.claude/CLAUDE.md`** — rewritten to describe the current architecture (PTY bridge, xterm.js, stock CLI) instead of the removed custom frontend and server.
- **`.dockerignore`** — removed references to deleted root-level files.

---

## 1.0.0 — Hermes Agent Gateway

**2026-03-10**

Added a second deployable app — `gateway/` — that runs the stock Hermes agent CLI in a browser-accessible web terminal. This gives full access to the native `hermes chat` experience (multiline editing, slash commands, rich output, tool use) from any browser, without installing anything locally. Deployed to the same Fly.io machine as the custom web terminal; the two apps share the monorepo but deploy independently.

### Added

- **Web terminal gateway** (`gateway/`) — a self-contained FastAPI app that spawns the `hermes` CLI in a real pseudo-terminal (PTY) and bridges it to the browser via xterm.js over WebSocket. Replaces the initially considered `ttyd` approach with a custom ~120-line Python PTY bridge, giving full control over auth and UI.
- **Styled login page** (`gateway/static/login.html`) — cookie-based authentication with HMAC-signed session tokens, replacing the browser's native HTTP Basic Auth popup. Matches the Evangelion design language: dark panels, red corner accents, scanline overlay, IBM Plex Mono typography.
- **Provider switcher** (`gateway/static/terminal.html`) — header dropdown to choose between Nous Direct and OpenRouter before connecting. Each session can use a different provider without redeploying. Spawns `hermes chat --provider <choice>` per session.
- **xterm.js terminal** (`gateway/static/terminal.html`) — full terminal emulator in the browser with the project's color palette, PTY resize support, web link detection, and hidden scrollbar. Header shows connection status with live indicator; footer shows active provider and session start time.
- **Entrypoint script** (`gateway/entrypoint.sh`) — injects Fly.io secrets (`OPENROUTER_API_KEY`, `HERMES_API_KEY`, etc.) into the hermes `~/.hermes/.env` config at container boot, bridging Fly's secret management to the CLI's expected config format.
- **Dockerfile** (`gateway/Dockerfile`) — clones `hermes-agent` with all extras (`pip install -e ".[all]"`), installs FastAPI + uvicorn, scaffolds the `~/.hermes/` directory structure the CLI expects, and copies the web app.
- **Fly.io config** (`gateway/fly.toml`) — targets the existing `hermes-terminal` app with `min_machines_running: 0` for cost efficiency (cold-starts on first visit). 1GB RAM to support concurrent CLI sessions.
- **Docker Compose** (`gateway/docker-compose.yml`) — local testing on port 8081, reads from the shared `.env` file.
- **Makefile targets** — `gateway-up`, `gateway-down`, `gateway-deploy`, `gateway-logs`, `gateway-ssh`, `gateway-status` mirror the existing web terminal commands.

### Architecture

The gateway is fully independent from the custom web terminal (`server/` + `frontend/`). Both live in the same monorepo and deploy to the same Fly.io app — `make deploy` ships the custom web terminal, `make gateway-deploy` ships the stock CLI gateway. Only one can be active at a time on the shared machine.

The PTY bridge works by calling `pty.openpty()` to create a master/slave pair, spawning `hermes chat` attached to the slave fd, then using `asyncio`'s `add_reader()` on the master fd to asynchronously shuttle bytes between the PTY and the WebSocket. Terminal resize events are forwarded via `TIOCSWINSZ` ioctl. Each browser tab gets an independent hermes process and conversation.

---

## 0.4.1 — Agent Timeout Guard

**2026-03-10**

The agent could hang indefinitely when the upstream LLM API was overloaded or returned non-retryable errors (e.g. OpenRouter 404 "no endpoints found that support tool use"). The Hermes agent's internal retry loop would keep cycling through its multi-step reasoning phases, each hitting the same dead API, while the WebSocket client received no feedback at all.

### Fixed

- **Infinite hang on API failure** (`server/main.py`) — wrapped `run_conversation()` in `asyncio.wait_for()` with a 90-second default timeout. When the agent exceeds this, the client receives a clear `AGENT TIMEOUT` system message advising to retry or switch models. The stale agent instance is discarded to prevent a zombie thread from interfering with the next request.

### Added

- **`HERMES_AGENT_TIMEOUT`** env var — configurable timeout in seconds (default `90`). Can be tuned per deployment via `.env` or Fly.io secrets.
- **`HERMES_API_KEY`** deployed to Fly.io — the Nous Research direct inference provider is now live, bypassing OpenRouter entirely for Nous models.

### Changed

- **Nous provider model list** (`server/main.py`) — updated from Hermes 3 (70B, DeepHermes 8B) to Hermes 4 (405B, 70B) to match the current Nous inference API. The 405B is now available directly through Nous without needing OpenRouter.

---

## 0.4.0 — Frontend Overhaul

**2026-03-10**

Complete frontend rewrite from a 3-file prototype to a modular, production-grade terminal UI. Deepens the Evangelion retrofuturist aesthetic with layered atmospheric effects, structured message rendering, and a strict design token system — while staying zero-dependency vanilla JS with no build step. See [`completions/001-frontend-overhaul.md`](completions/001-frontend-overhaul.md) for full implementation notes.

### Added

- **Boot sequence** (`js/boot.js`, `css/base.css`) — cinematic startup animation with sequential line reveals ("INITIALIZING NEURAL LINK... OK") before the terminal fades in. Skipped under `prefers-reduced-motion`.
- **Custom model selector** (`js/model-selector.js`, `css/model-selector.css`) — replaces the native `<select>` with a fully styled dropdown panel. Models grouped by provider with size/provider tags, amber accent glow, full keyboard navigation (Arrow keys, Enter, Escape), click-outside dismiss.
- **Telemetry strip** (`css/footer.css`) — thin ornamental bar between output and input showing message count, iteration placeholder, and latency placeholder. Animated amber sweep bar during processing state.
- **Status footer** (`js/telemetry.js`, `css/footer.css`) — persistent bar with version string, live clock (updates every second), and connection state indicator: `● READY` (green), `● PROCESSING` (amber, pulsing), `● LINK SEVERED` (red, pulsing).
- **Uptime counter** (`js/telemetry.js`) — `T+HH:MM:SS` in the header center, tracking time since WebSocket connect.
- **Structured messages** (`js/messages.js`, `css/output.css`) — each message now has a gutter (3-digit index + type-colored bar), body, and metadata row (timestamp, model name). Type bars: amber (system), blue (user), red (assistant).
- **Markdown rendering** (`js/messages.js`) — assistant messages rendered with safe markdown: code blocks, inline code, bold, italic, links (http/https only). HTML-escaped first, then regex-transformed — no XSS vectors. User/system messages use `textContent`.
- **Copy to clipboard** (`js/messages.js`, `css/output.css`) — assistant messages show a COPY button on hover. Click copies raw text; button briefly shows "COPIED" in green.
- **Smart auto-scroll** (`js/messages.js`) — detects when user has scrolled up to read history. New messages arrive without forcing scroll; a "NEW MESSAGES ▾" button appears to jump back to bottom.
- **Atmospheric overlays** (`css/base.css`) — three stacking layers: scanlines (5% opacity), SVG fractal noise texture (2.5% opacity), and radial vignette (35% at edges). All `pointer-events: none`, disabled on mobile for performance.
- **Corner accents** (`css/base.css`) — four decorative L-shaped corner marks in `--red-dim` on the terminal frame.
- **Multiline input** — `<textarea>` replaces `<input>`, auto-resizes on typing (up to 6em max). Enter submits, Shift+Enter for newlines. Command counter in left gutter, `[ENTER]` hint on right.
- **Input focus/processing states** (`css/input.css`) — bottom border glows blue on focus, pulses amber during processing.
- **Message transitions** (`css/animations.css`) — new messages fade in with `opacity 0→1` + subtle `translateX(-4px→0)` over 150ms.
- **Responsive breakpoints** (`css/responsive.css`) — 768px (header collapses, centered layout) and 480px (border frame removed, telemetry hidden, CRT effects disabled, larger touch targets).
- **Accessibility** — semantic HTML (`<header>`, `<main>`, `<footer>`), ARIA roles (`log`, `listbox`, `option`), `aria-live="polite"`, `aria-expanded`, `aria-label` on all interactive elements, `prefers-reduced-motion` support (all animations disabled, overlays hidden, boot skipped).

### Changed

- **Typography** — switched from system `Courier New`/`Consolas` to IBM Plex Mono (Google Fonts CDN). Strict 5-level type scale from 9px to 16px. All UI chrome uppercase with tracked letter-spacing.
- **Design token system** (`css/tokens.css`) — all visual values extracted into CSS custom properties: 5 background depth layers, 4 accent colors × 3 tiers (full/dim/glow), 3 border tiers, 4px-base spacing scale, transition timing tokens.
- **Header** (`css/header.css`) — redesigned as 3-column CSS grid (logo | status+sync+uptime | model selector). Bottom border glow via gradient pseudo-element; shifts red on disconnect.
- **Processing indicator** — replaced verbose "PROCESSING..." text with minimal `···`, plus multi-indicator feedback across telemetry strip, input bar, and status footer.
- **Connection resilience** (`js/connection.js`) — exponential backoff reconnection (1s → 2s → 4s → ... → 30s max), reset on successful connect. Replaces fixed 3-second retry.
- **State management** (`js/terminal.js`) — centralised state object with `getState()`/`setState(patch)` and observer pattern via `subscribe()`. Replaces scattered global variables.
- **Max width** — terminal container widened from 960px to 1080px.
- **Scrollbar** — custom 4px-wide scrollbar with `--blue-dim` thumb on hover.

### Architecture

- **ES modules** — `frontend/main.js` (monolithic, 145 lines) replaced by 7 native ES modules in `frontend/js/` (~800 lines total). Clean dependency graph with no circular imports: `terminal.js` (leaf) → `connection.js`, `messages.js`, `telemetry.js`, `boot.js` → `model-selector.js` → `main.js` (entry).
- **CSS modules** — `frontend/style.css` (228 lines) refactored into 9 CSS files in `frontend/css/` (~450 lines total), imported via a single `style.css` entry point using `@import`.
- **No new dependencies** — remains zero-dep vanilla JS. No build step, no bundler, no framework. IBM Plex Mono loaded via Google Fonts CDN.

### Removed

- **`frontend/main.js`** (root-level) — replaced by `frontend/js/main.js` ES module entry point.
- **Native `<select>` model dropdown** — replaced by custom dropdown component.

---

## 0.3.1 — Model Dropdown Loading Fix

**2026-03-10**

The model selector dropdown in the terminal header could get stuck on "LOADING..." indefinitely, particularly when the Fly.io machine was waking from auto-stop. The root cause was that the WebSocket connection was chained after the model fetch — if the fetch hung, the entire terminal was unresponsive.

### Fixed

- **Perpetual "LOADING..." dropdown** (`frontend/main.js`) — decoupled `loadModels()` from `connect()` so they run in parallel. The terminal now connects immediately while models load in the background.
- **Fetch timeout** (`frontend/main.js`) — added an 8-second `AbortController` timeout to the `/api/models` fetch. On timeout or error the dropdown shows "UNAVAILABLE" instead of hanging on "LOADING..." forever.
- **Late config sync** (`frontend/main.js`) — if the WebSocket connects before models finish loading, the selected model config is now sent once `loadModels()` completes, ensuring the server always knows the active model.

### Changed

- **`frontend/main.js`** — empty provider responses now show "NO MODELS" instead of leaving the dropdown blank.

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
