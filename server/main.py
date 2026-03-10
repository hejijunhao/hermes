import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

log = logging.getLogger("hermes")

app = FastAPI()

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# --- Hermes agent configuration ---
DEFAULT_MODEL = os.getenv("LLM_MODEL", "nousresearch/hermes-3-llama-3.1-405b")
HERMES_MAX_ITERATIONS = int(os.getenv("HERMES_MAX_ITERATIONS", "10"))
AGENT_TIMEOUT = int(os.getenv("HERMES_AGENT_TIMEOUT", "90"))

# --- Provider configurations ---
# Each provider maps to a base_url + api_key + list of available models.
PROVIDERS = {
    "nous": {
        "label": "Nous Research",
        "base_url": "https://inference-api.nousresearch.com/v1",
        "api_key_env": "HERMES_API_KEY",
        "models": [
            {"id": "Hermes-4-405B", "label": "Hermes 4 405B"},
            {"id": "Hermes-4-70B", "label": "Hermes 4 70B"},
        ],
    },
    "openrouter": {
        "label": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "models": [
            {"id": "nousresearch/hermes-3-llama-3.1-405b", "label": "Hermes 3 405B"},
            {"id": "nousresearch/hermes-3-llama-3.1-70b", "label": "Hermes 3 70B"},
            {"id": "anthropic/claude-sonnet-4", "label": "Claude Sonnet 4"},
            {"id": "google/gemini-2.5-pro-preview", "label": "Gemini 2.5 Pro"},
            {"id": "moonshotai/kimi-k2.5", "label": "Kimi K2.5"},
        ],
    },
}

# Filter to providers that have a key configured
def _available_providers():
    return {
        pid: prov for pid, prov in PROVIDERS.items()
        if os.getenv(prov["api_key_env"], "")
    }


def _create_agent(model: str = None, provider_id: str = None):
    """Create a fresh AIAgent instance for a single session."""
    from run_agent import AIAgent

    providers = _available_providers()
    prov = providers.get(provider_id) if provider_id else None

    kwargs = dict(
        model=model or DEFAULT_MODEL,
        quiet_mode=True,
        skip_context_files=True,
        skip_memory=True,
        max_iterations=HERMES_MAX_ITERATIONS,
        disabled_toolsets=["terminal"],
    )

    if prov:
        kwargs["base_url"] = prov["base_url"]
        kwargs["api_key"] = os.getenv(prov["api_key_env"], "")

    return AIAgent(**kwargs)


@app.get("/")
async def index():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/models")
async def list_models():
    """Return available providers and models for the frontend dropdown."""
    providers = _available_providers()
    result = []
    for pid, prov in providers.items():
        result.append({
            "id": pid,
            "label": prov["label"],
            "models": prov["models"],
        })
    return JSONResponse(result)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await ws.send_json({"type": "system", "content": "HERMES LINK ESTABLISHED"})

    loop = asyncio.get_running_loop()
    agent = None
    conversation_history = []
    current_model = DEFAULT_MODEL
    current_provider = None

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type", "user")

            # Handle model/provider config messages
            if msg_type == "config":
                new_model = data.get("model", current_model)
                new_provider = data.get("provider", current_provider)
                if new_model != current_model or new_provider != current_provider:
                    current_model = new_model
                    current_provider = new_provider
                    agent = None  # force re-creation
                    conversation_history = []
                    await ws.send_json({
                        "type": "system",
                        "content": f"MODEL SWITCHED: {current_model}",
                    })
                continue

            user_msg = data.get("content", "")

            # Lazily create agent on first message (or after model switch)
            if agent is None:
                agent = _create_agent(model=current_model, provider_id=current_provider)

            # Tell the client we're working
            await ws.send_json({"type": "system", "content": "PROCESSING..."})

            try:
                # AIAgent.run_conversation() is synchronous — run in a thread.
                # Wrapped in wait_for() so a hung upstream API doesn't block
                # the WebSocket indefinitely (the client would see nothing).
                result = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: agent.run_conversation(
                            user_message=user_msg,
                            conversation_history=conversation_history,
                        ),
                    ),
                    timeout=AGENT_TIMEOUT,
                )

                reply = result.get("final_response", "")
                conversation_history = result.get("messages", conversation_history)

                await ws.send_json({"type": "assistant", "content": reply})

            except asyncio.TimeoutError:
                log.warning("Agent timed out after %ds", AGENT_TIMEOUT)
                agent = None  # discard — the thread may still be running
                await ws.send_json({
                    "type": "system",
                    "content": f"AGENT TIMEOUT: No response after {AGENT_TIMEOUT}s. "
                               "The upstream API may be overloaded — try again or "
                               "switch models.",
                })

            except Exception as e:
                log.exception("Agent error")
                await ws.send_json({
                    "type": "system",
                    "content": f"AGENT ERROR: {e}",
                })

    except WebSocketDisconnect:
        pass


# Serve static frontend assets (must be mounted last)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
