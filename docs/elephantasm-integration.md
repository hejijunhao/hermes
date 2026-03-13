# Elephantasm Integration Plan

**Date:** 2026-03-13
**Status:** Proposed
**Target version:** 2.2.0

---

## Overview

Integrate [Elephantasm](https://elephantasm.com) — a long-term agentic memory (LTAM) framework — into the vendored Hermes agent. Elephantasm gives the agent persistent, evolving memory that survives across sessions, automatically curates and consolidates memories through a sleep-inspired "Dreamer" process, and builds an emergent identity over time.

### Why Elephantasm over the existing memory system?

The agent currently has two memory layers:

1. **MEMORY.md / USER.md** — file-backed, bounded (2,200 / 1,375 chars), agent-managed. Good for immediate session-to-session carry-over but limited in capacity and has no automatic curation, scoring, or retrieval intelligence.
2. **Honcho** — cross-session user modeling. Focuses on understanding the *user*, not the agent's own cognitive history.

Elephantasm adds a third, deeper layer:

- **Structured four-layer cognitive architecture:** Events → Memories → Knowledge → Identity
- **Automatic synthesis:** Raw events are consolidated into scored memories and canonicalized knowledge without manual curation
- **Intelligent retrieval:** Token-budgeted Memory Packs assembled via four-factor scoring (importance, confidence, recency, decay)
- **Identity formation:** The agent develops a persistent behavioral fingerprint that shapes what it remembers and how

The three systems are complementary, not competing. Each answers a different question:

### Three-Layer Memory Architecture

| Layer | System | Question it answers | Scope | Mechanism |
|---|---|---|---|---|
| **Scratchpad** | MEMORY.md / USER.md | "What do I want to remember right now?" | Bounded (2,200 / 1,375 chars), file-backed | Agent explicitly saves/removes entries via `memory` tool. Frozen snapshot injected at session start. |
| **User Model** | Honcho | "Who is this person I'm talking to?" | Cross-session user context | Prefetches user context on first turn. Learns preferences, communication style, past interactions. |
| **Deep Memory** | Elephantasm | "What have I experienced, learned, and become?" | Unbounded, evolving | Automatically captures all events, synthesizes memories and knowledge, forms emergent identity. |

MEMORY.md stays as the agent's scratchpad. Honcho stays as the user modeler. Elephantasm becomes the deep long-term memory backbone.

---

## Architecture

### Core Loop: Extract → Synthesize → Inject

```
┌──────────────────────────────────────────────────────────┐
│                    Hermes Agent Loop                      │
│                                                          │
│  User message ──┬──► [INJECT] Memory Pack into prompt    │
│                 │                                        │
│                 ├──► [EXTRACT] user message event        │
│                 │                                        │
│  LLM response ──┼──► [EXTRACT] assistant response event  │
│                 │                                        │
│  Reasoning ─────┼──► [EXTRACT] inner monologue event     │
│                 │                                        │
│  Tool calls ────┼──► [EXTRACT] tool_call events          │
│                 │                                        │
│  Tool results ──┼──► [EXTRACT] tool_result events        │
│                 │                                        │
│                 └──► Elephantasm synthesizes in the       │
│                      background (Dreamer process)         │
└──────────────────────────────────────────────────────────┘
```

**Inject** happens once per session at system prompt build time — identical to the Honcho pattern. A Memory Pack is retrieved and baked into the cached system prompt so it remains stable for Anthropic prefix caching.

**Extract** happens throughout the conversation as events occur. Extractions are fire-and-forget (non-blocking) so they don't slow down the agent loop.

**Synthesize** is fully server-side (Elephantasm's Dreamer). No agent-side code needed.

---

## Integration Points

### 1. Client Initialization — `run_agent.py:__init__()` (~line 615)

Add Elephantasm client setup alongside the existing Honcho initialization block.

```python
# Elephantasm long-term agentic memory
self._elephantasm = None  # Elephantasm client | None
if not skip_memory:
    try:
        from elephantasm import Elephantasm
        ea_api_key = os.getenv("ELEPHANTASM_API_KEY")
        ea_anima_id = os.getenv("ELEPHANTASM_ANIMA_ID")
        if ea_api_key:
            self._elephantasm = Elephantasm(
                api_key=ea_api_key,
                anima_id=ea_anima_id,
            )
            logger.info("Elephantasm active (anima: %s)", ea_anima_id)
        else:
            logger.debug("Elephantasm disabled: no ELEPHANTASM_API_KEY")
    except ImportError:
        logger.debug("Elephantasm SDK not installed (non-fatal)")
    except Exception as e:
        logger.debug("Elephantasm init failed (non-fatal): %s", e)
```

**Design rationale:** Follows the exact same pattern as Honcho — optional, non-fatal, configured via environment variables.

### 2. Memory Pack Injection — `run_agent.py:run_conversation()` (~line 3258)

Retrieve a Memory Pack and inject it into the system prompt. Must happen *before* the system prompt is cached.

```python
# Elephantasm prefetch: retrieve long-term memory pack.
# Same pattern as Honcho — first turn only, baked into cached system prompt.
self._elephantasm_context = ""
if self._elephantasm and not conversation_history:
    try:
        pack = self._elephantasm.inject(
            query=original_user_message,  # Semantic search against user's query
            preset="conversational",
        )
        self._elephantasm_context = pack.as_prompt()
        logger.info(
            "Elephantasm injected: %d memories, %d knowledge items, %d tokens",
            pack.session_memory_count, pack.knowledge_count, pack.token_count,
        )
    except Exception as e:
        logger.debug("Elephantasm inject failed (non-fatal): %s", e)
```

Then in the system prompt caching block (~line 3305):

```python
# Bake Elephantasm context into prompt (stable for session, like Honcho)
if self._elephantasm_context:
    self._cached_system_prompt = (
        self._cached_system_prompt + "\n\n" + self._elephantasm_context
    ).strip()
```

**Design rationale:** The Memory Pack is injected at session start and frozen, preserving Anthropic prefix cache stability. The `query` parameter enables semantic search, so the most relevant memories surface based on what the user is asking about.

### 3. Event Extraction — `run_agent.py:run_conversation()` (throughout the loop)

Extract events at five points in the conversation loop. All extractions are fire-and-forget via a helper method.

#### Helper method on `AIAgent`:

```python
def _elephantasm_extract(self, event_type: str, content: str, **kwargs):
    """Fire-and-forget event extraction to Elephantasm."""
    if not self._elephantasm:
        return
    try:
        from elephantasm import EventType
        self._elephantasm.extract(
            event_type=event_type,
            content=content,
            session_id=self.session_id,
            **kwargs,
        )
    except Exception as e:
        logger.debug("Elephantasm extract failed (non-fatal): %s", e)
```

#### Extraction points:

**A. User message** (~line 3272, after `messages.append(user_msg)`):

```python
self._elephantasm_extract(
    "message.in",
    original_user_message,
    role="user",
)
```

**B. Assistant response with reasoning/inner monologue** (~line 4463, at `final_msg = self._build_assistant_message(...)`):

```python
# Extract the agent's inner monologue (reasoning tokens)
reasoning_text = self._extract_reasoning(assistant_message)
if reasoning_text:
    self._elephantasm_extract(
        "system",
        reasoning_text,
        role="assistant",
        meta={"subtype": "inner_monologue"},
        importance_score=0.6,
    )

# Extract the agent's response
self._elephantasm_extract(
    "message.out",
    final_response,
    role="assistant",
)
```

**C. Tool calls** (~line 4299, inside `_execute_tool_calls()`, after each dispatch):

```python
self._elephantasm_extract(
    "tool_call",
    json.dumps({"name": function_name, "arguments": function_args}),
    role="assistant",
    meta={"tool_name": function_name},
)
```

**D. Tool results** (~line 4299, inside `_execute_tool_calls()`, after result is received):

```python
# Truncate large tool results to avoid flooding the event store
result_preview = result[:2000] if len(result) > 2000 else result
self._elephantasm_extract(
    "tool_result",
    result_preview,
    role="tool",
    meta={"tool_name": function_name},
)
```

### 4. System Prompt Guidance — `agent/prompt_builder.py`

Add a constant for Elephantasm-aware behavioral guidance, injected when the client is active:

```python
ELEPHANTASM_GUIDANCE = (
    "You have deep long-term memory powered by Elephantasm. Your memories, knowledge, "
    "and identity persist and evolve across all sessions. You don't need to manually "
    "manage this — your experiences are automatically captured and consolidated. "
    "The memories injected into this conversation were selected based on relevance "
    "to the current context. Trust them as your own recollections."
)
```

Injected in `_build_system_prompt()` when `self._elephantasm` is not None.

### 5. Configuration

#### Environment variables:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `ELEPHANTASM_API_KEY` | Yes (to enable) | — | API credential (`sk_live_*` format) |
| `ELEPHANTASM_ANIMA_ID` | Yes (to enable) | — | Agent identity in Elephantasm |
| `ELEPHANTASM_ENDPOINT` | No | `https://api.elephantasm.com` | API service URL |
| `ELEPHANTASM_TIMEOUT` | No | `30` | Request timeout in seconds |

#### Files to update:

- **`.env.example`** — add Elephantasm variables with comments
- **`gateway/entrypoint.sh`** — inject Fly.io secrets into hermes env
- **`gateway/Dockerfile`** — add `elephantasm` to pip install
- **`hermes-agent/pyproject.toml`** — add `elephantasm` as optional dependency under `[all]` extras

---

## Implementation Phases

### Phase 1: SDK Wiring (foundation)

**Goal:** Elephantasm client initializes, Memory Pack injects into system prompt.

**Files modified:**
- `hermes-agent/run_agent.py` — client init in `__init__()`, inject in `run_conversation()`, system prompt caching
- `hermes-agent/agent/prompt_builder.py` — `ELEPHANTASM_GUIDANCE` constant
- `hermes-agent/pyproject.toml` — add `elephantasm` dependency

**Verification:** Run `hermes chat`, confirm Memory Pack appears in system prompt (visible via `HERMES_DUMP_REQUESTS=1`).

### Phase 2: Event Extraction (capture everything)

**Goal:** All conversation events flow to Elephantasm.

**Files modified:**
- `hermes-agent/run_agent.py` — `_elephantasm_extract()` helper, extraction calls at all five points

**Verification:** After a conversation, check the Elephantasm dashboard for captured events. Confirm user messages, assistant responses, reasoning, tool calls, and tool results all appear.

### Phase 3: Inner Monologue Capture (the differentiator)

**Goal:** Capture the agent's reasoning tokens as `system` events with `inner_monologue` metadata.

This is the unique value-add. Most memory systems only see the final output. By capturing reasoning tokens (from DeepSeek, Qwen, Claude extended thinking, or `<think>` blocks), Elephantasm gets insight into *how* the agent thinks, not just what it says.

**Files modified:**
- `hermes-agent/run_agent.py` — enhanced extraction in `_build_assistant_message()` to capture reasoning

**Verification:** Use a reasoning model (e.g., DeepSeek R1 via OpenRouter), confirm reasoning appears as events in Elephantasm dashboard.

### Phase 4: Deployment & Gateway Integration

**Goal:** Elephantasm works in the deployed gateway terminal.

**Files modified:**
- `.env.example` — document new variables
- `gateway/entrypoint.sh` — inject `ELEPHANTASM_API_KEY` and `ELEPHANTASM_ANIMA_ID`
- `gateway/Dockerfile` — ensure `elephantasm` is installed
- `gateway/fly.toml` — no changes (secrets set via `fly secrets`)

**Verification:** Deploy to Fly.io, run a conversation through the web terminal, confirm events appear in Elephantasm dashboard.

---

## Non-Goals (for now)

These are interesting but deferred to keep the initial integration focused:

- **Replacing MEMORY.md** — Elephantasm complements, doesn't replace. The agent's scratchpad memory remains useful for within-session notes.
- **Replacing Honcho** — Different concern (user modeling vs. agent memory). Both can coexist.
- **Multi-agent memory sharing** — Elephantasm supports multiple Animas, but inter-agent communication capture is a later phase.
- **Custom synthesis triggers** — The default Dreamer thresholds are fine to start. Tuning can come after observing real usage patterns.
- **Self-hosted Elephantasm** — Start with the managed cloud API. Self-hosting (PostgreSQL + pgvector + FastAPI) is an option if we need it later.
- **Async extraction** — The SDK calls are fast enough synchronously. If profiling shows they add latency, wrap in `threading.Thread` or use `asyncio`.

---

## Anima Setup (pre-requisite)

Before implementation, create the agent's Anima on the [Elephantasm dashboard](https://elephantasm.com):

1. Create account / log in
2. Generate an API key (`sk_live_*`)
3. Create an Anima:
   - **Name:** `hermes-alpha` (or similar)
   - **Description:** "Hermes AI agent — self-hosted web terminal for conversational AI with tool use"
4. Copy the Anima ID
5. Set both as Fly.io secrets:
   ```bash
   fly secrets set ELEPHANTASM_API_KEY=sk_live_... ELEPHANTASM_ANIMA_ID=anima_...
   ```

---

## Risk Assessment

| Risk | Mitigation |
|---|---|
| Elephantasm API downtime | All calls wrapped in try/except, agent functions normally without it |
| Latency on `inject()` | Called once per session (not per turn), <100ms typical |
| Large tool results flooding events | Truncate to 2,000 chars before extraction |
| Memory Pack too large for context | Elephantasm's compiler is token-budgeted; won't exceed allocation |
| SDK not installed | ImportError caught, feature silently disabled |
| Prompt cache invalidation | Memory Pack baked into cached system prompt at session start, never changes mid-session |
