import asyncio
import fcntl
import hashlib
import hmac
import json
import logging
import os
import pty
import secrets
import struct
import termios
from pathlib import Path

from fastapi import FastAPI, WebSocket, Request, Form
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("hermes.web")

app = FastAPI()

STATIC_DIR = Path(__file__).parent / "static"

AUTH_PASS = os.getenv("TTYD_PASS", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_hex(32))
COOKIE_NAME = "hermes_session"


def _make_token():
    return hmac.new(
        SESSION_SECRET.encode(), AUTH_PASS.encode(), hashlib.sha256
    ).hexdigest()


def _is_authed(request: Request) -> bool:
    return request.cookies.get(COOKIE_NAME) == _make_token()


# ── Routes ───────────────────────────────────────────────


@app.get("/")
async def index(request: Request):
    if _is_authed(request):
        return RedirectResponse("/terminal")
    return FileResponse(STATIC_DIR / "login.html")


@app.post("/login")
async def login(password: str = Form(...)):
    if password == AUTH_PASS:
        resp = RedirectResponse("/terminal", status_code=303)
        resp.set_cookie(
            COOKIE_NAME, _make_token(),
            httponly=True, secure=True, samesite="strict", max_age=86400,
        )
        return resp
    return RedirectResponse("/?error=1", status_code=303)


@app.get("/terminal")
async def terminal_page(request: Request):
    if not _is_authed(request):
        return RedirectResponse("/")
    return FileResponse(STATIC_DIR / "terminal.html")


# ── PTY helpers ──────────────────────────────────────────


async def _spawn_pty_async(cmd: list[str]):
    """Spawn a command in a new PTY (async version). Returns (process, master_fd)."""
    master_fd, slave_fd = pty.openpty()
    env = {**os.environ, "TERM": "xterm-256color"}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid,
        env=env,
    )
    os.close(slave_fd)

    # Non-blocking reads on master
    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    return proc, master_fd


def _cleanup_pty(loop, master_fd, proc):
    """Safely clean up PTY resources."""
    try:
        loop.remove_reader(master_fd)
    except Exception:
        pass
    try:
        os.close(master_fd)
    except OSError:
        pass
    try:
        proc.terminate()
    except ProcessLookupError:
        pass


# ── WebSocket PTY Bridge ─────────────────────────────────


@app.websocket("/ws")
async def ws_terminal(ws: WebSocket, provider: str = "openrouter"):
    if ws.cookies.get(COOKIE_NAME) != _make_token():
        await ws.close(code=4001)
        return

    await ws.accept()

    # Build command — provider flag goes after the "chat" subcommand
    cmd = ["hermes", "chat"]
    if provider in ("nous", "openrouter"):
        cmd.extend(["--provider", provider])

    proc, master_fd = await _spawn_pty_async(cmd)
    logger.info("PTY spawned: pid=%s cmd=%s", proc.pid, cmd)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _on_pty_data():
        try:
            data = os.read(master_fd, 65536)
            if data:
                queue.put_nowait(data)
            else:
                queue.put_nowait(None)
        except OSError:
            queue.put_nowait(None)

    loop.add_reader(master_fd, _on_pty_data)

    async def _watch_proc():
        """Monitor the child process and signal the queue when it exits."""
        retcode = await proc.wait()
        logger.warning("PTY process exited: pid=%s retcode=%s", proc.pid, retcode)
        queue.put_nowait(None)

    async def pty_to_ws():
        while True:
            data = await queue.get()
            if data is None:
                # PTY died — notify the browser and close the WebSocket
                try:
                    await ws.send_text(
                        "\r\n\x1b[31m[hermes process exited — refresh to reconnect]\x1b[0m\r\n"
                    )
                    await ws.close(code=1000, reason="PTY exited")
                except Exception:
                    pass
                break
            try:
                await ws.send_text(data.decode("utf-8", errors="replace"))
            except Exception:
                break

    async def ws_to_pty():
        try:
            while True:
                msg = await ws.receive()
                if msg["type"] == "websocket.disconnect":
                    break
                text = msg.get("text", "")
                if not text:
                    continue
                # Handle resize messages from xterm.js
                if text.startswith("{"):
                    try:
                        payload = json.loads(text)
                        if payload.get("type") == "resize":
                            winsize = struct.pack(
                                "HHHH", payload["rows"], payload["cols"], 0, 0
                            )
                            fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                            continue
                    except (json.JSONDecodeError, KeyError):
                        pass
                try:
                    os.write(master_fd, text.encode("utf-8"))
                except OSError:
                    # PTY fd is dead
                    break
        except Exception:
            pass

    watcher = asyncio.create_task(_watch_proc())
    task_pty = asyncio.create_task(pty_to_ws())
    task_ws = asyncio.create_task(ws_to_pty())

    try:
        # Wait for EITHER direction to finish, then cancel the other
        done, pending = await asyncio.wait(
            [task_pty, task_ws], return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
    finally:
        watcher.cancel()
        _cleanup_pty(loop, master_fd, proc)
        logger.info("WebSocket session cleaned up: pid=%s", proc.pid)


# Static assets (must be last)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
