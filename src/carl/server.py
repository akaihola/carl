"""Carl's server: the page, the WebSocket and the API (spec section 2).

Everything is behind the access-pass gate except `/api/health` and the pass
form itself. Every path under `/api/` skips the loading Worker, so the
WebSocket, the health poll and the API go straight through Cloudflare's
proxy.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import weakref
from dataclasses import asdict
from importlib import resources
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import WSCloseCode, WSMsgType, web

from . import gate, probe
from .config import Config
from .gate import Passes
from .link import Link
from .prompts import Prompt
from .session import Session, Sessions

log = logging.getLogger(__name__)

WEB = Path(str(resources.files("carl") / "web"))
OPEN_PATHS = {"/api/health", "/api/unlock"}
MAX_FRAME_BYTES = 1 << 20  # an audio chunk of about 100 ms is 3.2 kB

CONFIG = web.AppKey("config", Config)
PROMPTS = web.AppKey("prompts", dict[str, Prompt])
PASSES = web.AppKey("passes", Passes)
SOCKETS = web.AppKey("sockets", weakref.WeakSet[web.WebSocketResponse])
SESSIONS = web.AppKey("sessions", Sessions)

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


def create_app(config: Config, prompts: dict[str, Prompt], passes: Passes, sessions: Sessions) -> web.Application:
    app = web.Application(middlewares=[headers, access_pass])
    app[CONFIG] = config
    app[PROMPTS] = prompts
    app[PASSES] = passes
    app[SESSIONS] = sessions
    app[SOCKETS] = weakref.WeakSet()
    app.on_shutdown.append(close_sockets)
    app.router.add_get("/api/health", health)
    app.router.add_post("/api/unlock", unlock)
    app.router.add_get("/api/ws", websocket)
    app.router.add_get("/", index)
    app.router.add_static("/static", WEB)
    probe.setup(app)
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
    sessions = request.app[SESSIONS]
    link = Link(ws, config.connection.heartbeat_s, config.connection.silence_s)
    log.info("page connected")
    await link.send({"type": "hello", "config": config.page_values(), "costs": await sessions.month_costs()})
    keep_alive = asyncio.create_task(link.keep_alive())
    page = Page(link, sessions)
    try:
        async for message in ws:
            link.heard()
            if message.type is WSMsgType.BINARY:
                link.audio_bytes += len(message.data)
                if page.session is not None:
                    await page.session.audio(message.data)
            elif message.type is WSMsgType.TEXT:
                await page.on_message(message.data)
    finally:
        keep_alive.cancel()
        if page.session is not None:
            await page.session.detach(link)
        log.info(
            "page %s after %.0f s, %d audio bytes",
            "dropped" if link.dropped else "disconnected",
            link.loop.time() - link.opened,
            link.audio_bytes,
        )
    return ws


async def close_sockets(app: web.Application) -> None:
    """On a restart or scale-down, end the sessions, so their recordings are
    written out, and let pages go at once so they reconnect."""
    await app[SESSIONS].end_all("server shutdown")
    await app[SESSIONS].close()
    for ws in set(app[SOCKETS]):
        await ws.close(code=WSCloseCode.GOING_AWAY, message=b"server shutdown")


class Page:
    """One page's connection: its messages, and the session it drives."""

    def __init__(self, link: Link, sessions: Sessions) -> None:
        self.link, self.sessions = link, sessions
        self.session: Session | None = None

    async def send(self, message: dict) -> None:
        """A page may be gone by the time its answer is ready, as after `end` on pagehide."""
        with contextlib.suppress(ConnectionError):
            await self.link.send(message)

    async def on_message(self, data: str) -> None:
        try:
            message = json.loads(data)
            kind = message["type"]
        except (ValueError, TypeError, KeyError):
            log.warning("ignored a text frame that isn't a message: %.80r", data)
            return
        handler = getattr(self, "on_" + str(kind).replace("-", "_"), None)
        if handler is None:
            log.info("ignored a %r message", kind)
            return
        await handler(message)

    async def on_heartbeat(self, message: dict) -> None:
        pass

    async def on_start(self, message: dict) -> None:
        if self.session is not None and self.session.state != "ended":
            await self.send(self.session.state_message())
            return
        if (session_id := self.sessions.started_as(message)) is not None:
            await self.on_rejoin({"session": session_id})  # a start resent after a drop
            return
        self.session = await self.sessions.start(self.link, message)
        await self.send(self.session.state_message())
        await self.send(self.session.health.message())

    async def on_rejoin(self, message: dict) -> None:
        session_id = str(message.get("session", ""))
        session = self.sessions.get(session_id)
        if session is None:
            summary = self.sessions.ended.get(session_id)
            await self.send({"type": "ended", "session": session_id, "summary": summary and asdict(summary)})
            return
        self.session = session
        await session.attach(self.link)
        await self.send(session.state_message())
        await self.send(session.health.message())
        await session.send_cards()

    async def on_pause(self, message: dict) -> None:
        if self.session is not None:
            await self.session.pause()
            await self.send(self.session.state_message())

    async def on_resume(self, message: dict) -> None:
        if self.session is not None:
            await self.session.resume()
            await self.send(self.session.state_message())

    async def on_end(self, message: dict) -> None:
        if self.session is not None:
            session, self.session = self.session, None
            summary = await session.end("end")
            await self.send(summary.message(session.id))

    async def on_location(self, message: dict) -> None:
        if self.session is not None:
            await self.sessions.on_location(self.session, message)

    async def on_mic(self, message: dict) -> None:
        """The page's microphone: `lost` (with a `detail`) or `back`."""
        if self.session is not None:
            detail = message.get("detail")
            self.session.health.mic(str(message.get("state")), str(detail)[:64] if detail else None)

    async def on_page_events(self, message: dict) -> None:
        """What the page buffered while it couldn't tell the server."""
        if self.session is not None:
            self.session.health.page_events(message.get("events"))

    async def on_card_shown(self, message: dict) -> None:
        if self.session is not None:
            self.session.card_reported("shown", str(message.get("id", ""))[:20], message.get("at"))

    async def on_card_filed(self, message: dict) -> None:
        if self.session is not None:
            self.session.card_reported("filed", str(message.get("id", ""))[:20], message.get("at"),
                                       message.get("late") is True)

    async def on_stop_recording(self, message: dict) -> None:
        session_id = str(message.get("session", ""))
        if await self.sessions.stop_recording(session_id):
            await self.send({"type": "recording_stopped", "session": session_id})
            if self.session is not None and self.session.id == session_id:
                await self.send(self.session.state_message())
