"""One WebSocket between the page and the server (spec section 2, One WebSocket).

Binary frames carry audio and JSON text frames carry everything else. Each
side sends a heartbeat when it has sent nothing else for `heartbeat_s`, and a
side that hears nothing for `silence_s` treats the connection as dropped.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Close code for a connection dropped after silence. 4000-4999 are free for
# applications.
SILENCE_CLOSE = 4000


class Socket(Protocol):
    closed: bool

    async def send_str(self, data: str) -> None: ...
    async def close(self, *, code: int, message: bytes) -> Any: ...


class Link:
    def __init__(self, ws: Socket, heartbeat_s: float, silence_s: float):
        self.ws = ws
        self.heartbeat_s = heartbeat_s
        self.silence_s = silence_s
        self.loop = asyncio.get_running_loop()
        self.opened = self.last_sent = self.last_heard = self.loop.time()
        self.audio_bytes = 0
        self.dropped = False

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_str(json.dumps(message, ensure_ascii=False))
        self.last_sent = self.loop.time()

    def heard(self) -> None:
        """Anything at all from the page, a heartbeat or audio, counts."""
        self.last_heard = self.loop.time()

    async def keep_alive(self) -> None:
        """Send the heartbeat while idle, and drop the connection after silence."""
        try:
            while not self.ws.closed:
                now = self.loop.time()
                if now - self.last_heard >= self.silence_s:
                    self.dropped = True
                    log.info("no message from the page for %.0f s: connection dropped", now - self.last_heard)
                    await self.ws.close(code=SILENCE_CLOSE, message=b"silence")
                    return
                if now - self.last_sent >= self.heartbeat_s:
                    await self.send({"type": "heartbeat"})
                wake = min(self.last_sent + self.heartbeat_s, self.last_heard + self.silence_s)
                await asyncio.sleep(max(0.0, wake - self.loop.time()))
        except ConnectionError:
            pass  # the socket closed under us; the receiving side sees that too
