"""A CPU pace probe for the step-1 connection test (ticket 19).

Carl's checks must keep running while no page is connected, during the
reconnect grace period, so the container's CPU must not be throttled then.
`POST /api/probe?seconds=N` starts a ticker on the server that, every
100 ms, does a fixed piece of CPU work and records how long the work took
and how late the tick was. `GET /api/probe` returns the ticks. Comparing a
stretch with a page connected against one without shows any throttling.
Both routes are behind the access pass.
"""

from __future__ import annotations

import asyncio
import hashlib
import time

from aiohttp import web

TICK_S = 0.1
MAX_SECONDS = 600
WORK = b"\0" * (1 << 20)  # hashing 1 MB takes a few ms on an unthrottled vCPU
PROBE = web.AppKey("probe", dict)


def work() -> float:
    start = time.perf_counter()
    hashlib.sha256(WORK).digest()
    return time.perf_counter() - start


async def ticker(state: dict, seconds: float) -> None:
    loop = asyncio.get_running_loop()
    start = due = loop.time()
    while (now := loop.time()) - start < seconds:
        state["ticks"].append(
            {"t": round(time.time(), 3), "late_ms": round((now - due) * 1000, 2), "work_ms": round(work() * 1000, 2)}
        )
        due += TICK_S
        await asyncio.sleep(max(0.0, due - loop.time()))
    state["running"] = False


async def start(request: web.Request) -> web.Response:
    seconds = min(float(request.query.get("seconds", 60)), MAX_SECONDS)
    state = request.app[PROBE]
    if state.get("running"):
        raise web.HTTPConflict(text="A probe is running.")
    state.update(running=True, started=time.time(), seconds=seconds, ticks=[])
    state["task"] = asyncio.create_task(ticker(state, seconds))
    return web.json_response({"started": state["started"], "seconds": seconds})


async def results(request: web.Request) -> web.Response:
    state = request.app[PROBE]
    return web.json_response({k: v for k, v in state.items() if k != "task"})


def setup(app: web.Application) -> None:
    app[PROBE] = {}
    app.router.add_post("/api/probe", start)
    app.router.add_get("/api/probe", results)
