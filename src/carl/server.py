"""Carl's server: the page, the WebSocket and the API (spec section 2).

Everything is behind the access-pass gate except `/api/health` and the pass
form itself. Every path under `/api/` skips the loading Worker, so the
WebSocket, the health poll and the API go straight through Cloudflare's
proxy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import weakref
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSCloseCode, WSMsgType, web

from . import gate
from .config import Config
from .gate import Passes
from .link import Link
from .prompts import Prompt

log = logging.getLogger(__name__)

WEB = Path(str(resources.files("carl") / "web"))
OPEN_PATHS = {"/api/health", "/api/unlock"}
MAX_FRAME_BYTES = 1 << 20  # an audio chunk of about 100 ms is 3.2 kB

CONFIG = web.AppKey("config", Config)
PROMPTS = web.AppKey("prompts", dict[str, Prompt])
PASSES = web.AppKey("passes", Passes)
SOCKETS = web.AppKey("sockets", weakref.WeakSet[web.WebSocketResponse])

# The page makes no third-party calls, and this says so to the browser.
PAGE_CSP = (
    "default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
    "form-action 'self'; frame-ancestors 'none'"
)
# The pass form carries its own styles, since nothing behind the gate loads
# before the pass is accepted.
PASS_CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"

PASS_PAGE = """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Carl</title>
<style>
  body {{ margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0f1319; color: #e9edf2;
         font: 18px/1.5 "Atkinson Hyperlegible", Verdana, system-ui, sans-serif; }}
  form {{ display: grid; gap: .8em; width: min(22em, 100vw - 3em); }}
  h1 {{ margin: 0; font-size: 1.6em; }}
  input {{ font: inherit; color: inherit; background: #1b222c; border: 1px solid #2c3542;
          border-radius: 8px; padding: .6em .8em; }}
  button {{ font: inherit; font-weight: 700; border: 0; border-radius: 8px; padding: .6em;
           background: #8fd3a6; color: #0d1a12; }}
  p {{ margin: 0; color: #f08a5d; }}
</style>
<form method="post" action="/api/unlock">
  <h1>Carl</h1>
  <label for="pass">Access pass</label>
  <input id="pass" name="pass" type="password" autocomplete="current-password"
         autocapitalize="none" autocorrect="off" spellcheck="false" required autofocus>
  {error}
  <button>Open Carl</button>
</form>
</html>
"""


def create_app(config: Config, prompts: dict[str, Prompt], passes: Passes) -> web.Application:
    app = web.Application(middlewares=[headers, access_pass])
    app[CONFIG] = config
    app[PROMPTS] = prompts
    app[PASSES] = passes
    app[SOCKETS] = weakref.WeakSet()
    app.on_shutdown.append(close_sockets)
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/unlock", unlock)
    app.router.add_get("/api/ws", websocket)
    app.router.add_get("/", index)
    app.router.add_static("/static", WEB)
    return app


@web.middleware
async def access_pass(request: web.Request, handler) -> web.StreamResponse:
    if request.path in OPEN_PATHS or request.app[PASSES].valid(request.cookies.get(gate.COOKIE)):
        return await handler(request)
    if request.method == "GET" and not request.path.startswith("/api/"):
        return pass_page()
    raise web.HTTPUnauthorized(text="An access pass is needed.")


@web.middleware
async def headers(request: web.Request, handler) -> web.StreamResponse:
    try:
        response = await handler(request)
    except web.HTTPException as e:
        response = e
    if response.prepared:  # the WebSocket, already upgraded
        return response
    response.headers.setdefault("Content-Security-Policy", PAGE_CSP)
    # `private`: nothing behind the gate is kept in a shared cache such as
    # Cloudflare's, and `no-cache`: a browser revalidates, so a deploy shows
    # at once. `no-transform`: Cloudflare injects nothing, such as its
    # analytics beacon.
    response.headers.setdefault("Cache-Control", "private, no-cache")
    if "no-transform" not in response.headers["Cache-Control"]:
        response.headers["Cache-Control"] += ", no-transform"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if isinstance(response, web.HTTPException):
        raise response
    return response


def pass_page(error: bool = False) -> web.Response:
    text = PASS_PAGE.format(error="<p>That access pass didn’t work.</p>" if error else "")
    response = web.Response(text=text, status=401, content_type="text/html")
    response.headers["Content-Security-Policy"] = PASS_CSP
    response.headers["Cache-Control"] = "no-store"
    return response


async def health(request: web.Request) -> web.Response:
    """Cheap and without side effects: the loading page polls it."""
    return web.json_response({"ok": True}, headers={"Cache-Control": "no-store"})


async def unlock(request: web.Request) -> web.StreamResponse:
    form = await request.post()
    password = str(form.get("pass", "")).strip()[:1024]
    passes = request.app[PASSES]
    salt = await asyncio.to_thread(passes.check, password) if password else None
    if salt is None:
        await asyncio.sleep(gate.WRONG_PASS_WAIT_S)
        return pass_page(error=True)
    response = web.Response(status=303, headers={"Location": "/"})
    response.set_cookie(
        gate.COOKIE,
        passes.token(salt),
        max_age=gate.COOKIE_MAX_AGE_S,
        path="/",
        httponly=True,
        secure=True,
        samesite="Lax",
    )
    return response


async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse(WEB / "index.html")


def same_origin(request: web.Request) -> bool:
    """A browser names the page's origin on the upgrade; it must be Carl's own."""
    origin = request.headers.get("Origin")
    return origin is None or urlsplit(origin).netloc == request.host


async def websocket(request: web.Request) -> web.WebSocketResponse:
    if not same_origin(request):
        raise web.HTTPForbidden(text="Wrong origin.")
    config = request.app[CONFIG]
    ws = web.WebSocketResponse(max_msg_size=MAX_FRAME_BYTES)
    await ws.prepare(request)
    request.app[SOCKETS].add(ws)
    link = Link(ws, config.connection.heartbeat_s, config.connection.silence_s)
    log.info("page connected")
    await link.send({"type": "hello", "config": config.page_values()})
    keep_alive = asyncio.create_task(link.keep_alive())
    try:
        async for message in ws:
            link.heard()
            if message.type is WSMsgType.BINARY:
                link.audio_bytes += len(message.data)  # audio: used from step 2 on
            elif message.type is WSMsgType.TEXT:
                await on_message(link, message.data)
    finally:
        keep_alive.cancel()
        log.info(
            "page %s after %.0f s, %d audio bytes",
            "dropped" if link.dropped else "disconnected",
            link.loop.time() - link.opened,
            link.audio_bytes,
        )
    return ws


async def close_sockets(app: web.Application) -> None:
    """On a restart or scale-down, let pages go at once so they reconnect."""
    for ws in set(app[SOCKETS]):
        await ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown")


async def on_message(link: Link, data: str) -> None:
    try:
        message = json.loads(data)
        kind = message["type"]
    except (ValueError, TypeError, KeyError):
        log.warning("ignored a text frame that isn't a message: %.80r", data)
        return
    if kind != "heartbeat":
        log.info("ignored a %r message", kind)
