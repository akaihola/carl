#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["aiohttp>=3.12"]
# ///
"""Carl build step 1: the 2-hour connection test (ticket 19).

Measures, through Cloudflare's proxy to the Scaleway container:

1. the cold start: a page load through the loading Worker, then the health
   poll the loading page makes, until the container answers;
2. where the WebSocket is really cut: one WebSocket held for the whole run
   with the page's heartbeat, reconnecting at once after every cut;
3. whether the CPU is throttled while no page is connected: the server's
   CPU probe runs with the WebSocket open, and again with it closed and no
   request at all reaching the container.

Every event goes to out/<time>/events.jsonl, and a summary is printed at the
end. Start it only after the container has had 20 minutes without a request,
so the first request is a cold start (`--wait` sleeps first).

    uv run connection_test.py --hours 2 --wait 1200

The access pass is read from .secrets.access-passes.txt at the repo root.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = "https://faktat.vempai.men"  # --base changes it
HEARTBEAT_S = 3


class Log:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a")
        self.t0 = time.time()

    def __call__(self, event: str, **fields) -> dict:
        record = {"time": datetime.now(UTC).isoformat(timespec="milliseconds"), "t": round(time.time() - self.t0, 3),
                  "event": event, **fields}
        self.file.write(json.dumps(record) + "\n")
        self.file.flush()
        print(f"{record['t']:9.1f}  {event}  {json.dumps(fields)}", flush=True)
        return record


async def cold_start(session: aiohttp.ClientSession, log: Log) -> None:
    """Load the page as a browser would, then poll the health endpoint as the loading page does."""
    start = time.monotonic()
    log("cold start: page load")
    async with session.get(BASE + "/", headers={"Sec-Fetch-Mode": "navigate"}) as r:
        text = await r.text()
        log("page load answered", status=r.status, after_s=round(time.monotonic() - start, 2),
            loading_page="Starting up" in text)
    while True:
        try:
            async with session.get(BASE + "/api/health", timeout=aiohttp.ClientTimeout(total=110)) as r:
                if r.status == 200:
                    break
                log("health", status=r.status)
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            log("health failed", error=type(e).__name__)
        await asyncio.sleep(2)
    log("health answered", after_s=round(time.monotonic() - start, 2))


async def unlock(session: aiohttp.ClientSession, log: Log) -> None:
    passes = (ROOT / ".secrets.access-passes.txt").read_text()
    password = re.search(r"owner's phone: (\S+)", passes).group(1)
    async with session.post(BASE + "/api/unlock", data={"pass": password}, allow_redirects=False) as r:
        if r.status != 303:
            raise SystemExit(f"unlock failed: {r.status}")
        session.cookie_jar.update_cookies({"carl_pass": r.cookies["carl_pass"].value})
    log("unlocked")


class Holder:
    """Holds one WebSocket at a time, reconnecting after every cut, unless paused."""

    def __init__(self, session: aiohttp.ClientSession, log: Log):
        self.session, self.log = session, log
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.paused = asyncio.Event()
        self.stopped = False
        self.connections: list[dict] = []

    async def run(self) -> None:
        while not self.stopped:
            if self.paused.is_set():
                await asyncio.sleep(0.2)
                continue
            await self.hold_one()

    async def hold_one(self) -> None:
        opened = time.monotonic()
        try:
            ws = await self.session.ws_connect(BASE + "/api/ws", origin=BASE, heartbeat=None, receive_timeout=None)
        except aiohttp.ClientError as e:
            self.log("ws connect failed", error=repr(e))
            await asyncio.sleep(1)
            return
        self.ws = ws
        self.log("ws open", connect_s=round(time.monotonic() - opened, 2))
        opened = time.monotonic()
        beats = asyncio.create_task(self.beat(ws))
        received = 0
        last = None
        try:
            async for message in ws:
                received += 1
                last = time.monotonic()
        except Exception as e:  # noqa: BLE001
            self.log("ws error", error=repr(e))
        finally:
            beats.cancel()
        record = self.log(
            "ws closed", held_s=round(time.monotonic() - opened, 1), code=ws.close_code,
            reason=str(ws.exception()) if ws.exception() else None, messages=received,
            silent_before_close_s=round(time.monotonic() - last, 1) if last else None,
            ours=self.paused.is_set() or self.stopped,
        )
        self.connections.append(record)
        self.ws = None

    async def beat(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        while not ws.closed:
            await ws.send_json({"type": "heartbeat"})
            await asyncio.sleep(HEARTBEAT_S)

    async def pause(self) -> None:
        self.paused.set()
        if self.ws is not None:
            await self.ws.close()
        while self.ws is not None:
            await asyncio.sleep(0.1)

    def resume(self) -> None:
        self.paused.clear()


async def probe(session: aiohttp.ClientSession, log: Log, holder: Holder, name: str, seconds: float,
                disconnected_s: float) -> None:
    """Run the CPU probe; for `disconnected_s` of it, no page is connected and nothing reaches the server."""
    async with session.post(f"{BASE}/api/probe?seconds={seconds}") as r:
        started = (await r.json())["started"]
    log("probe started", name=name, seconds=seconds)
    windows = []
    await asyncio.sleep(10)
    if disconnected_s:
        await holder.pause()
        off = time.time()
        log("page gone", name=name)
        await asyncio.sleep(disconnected_s)
        on = time.time()
        windows.append((off, on))
        holder.resume()
        log("page back", name=name)
    await asyncio.sleep(max(0, started + seconds - time.time()) + 2)
    async with session.get(f"{BASE}/api/probe") as r:
        state = await r.json()
    ticks = state["ticks"]
    gone = [t for t in ticks if any(a + 1 <= t["t"] <= b for a, b in windows)]
    there = [t for t in ticks if t not in gone]
    log("probe result", name=name, ticks=len(ticks), expected=int(seconds / 0.1),
        connected=summary(there), disconnected=summary(gone), raw=ticks)


def summary(ticks: list[dict]) -> dict | None:
    if not ticks:
        return None
    work = sorted(t["work_ms"] for t in ticks)
    late = sorted(t["late_ms"] for t in ticks)
    span = ticks[-1]["t"] - ticks[0]["t"]
    return {
        "ticks": len(ticks), "ticks_per_s": round((len(ticks) - 1) / span, 2) if span else None,
        "work_ms_median": statistics.median(work), "work_ms_p95": work[int(len(work) * 0.95) - 1],
        "late_ms_median": statistics.median(late), "late_ms_p95": late[int(len(late) * 0.95) - 1],
        "late_ms_max": late[-1],
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--hours", type=float, default=2.0)
    parser.add_argument("--wait", type=float, default=0, help="seconds to sleep first, so the container is cold")
    parser.add_argument("--no-cold-start", action="store_true")
    parser.add_argument("--base", default=BASE, help="Carl's address (default: %(default)s)")
    parser.add_argument("--scale", type=float, default=1.0, help="shrink the probe plan, for a dry run")
    args = parser.parse_args()
    globals()["BASE"] = args.base.rstrip("/")

    out = HERE / "out" / datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log = Log(out / "events.jsonl")
    if args.wait:
        log("waiting for the container to go cold", seconds=args.wait)
        await asyncio.sleep(args.wait)
    async with aiohttp.ClientSession(trust_env=True, cookie_jar=aiohttp.CookieJar()) as session:
        if not args.no_cold_start:
            await cold_start(session, log)
        await unlock(session, log)
        holder = Holder(session, log)
        holding = asyncio.create_task(holder.run())
        end = time.monotonic() + args.hours * 3600
        # (minute, name, probe seconds, seconds with no page connected)
        plan = [(3, "connected", 60, 0), (6, "no page for 90 s", 150, 90), (70, "no page for 150 s", 200, 150)]
        for minute, name, seconds, gone in plan:
            wait = end - args.hours * 3600 + minute * 60 * args.scale - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            if time.monotonic() < end:
                await probe(session, log, holder, name, seconds * args.scale, gone * args.scale)
        await asyncio.sleep(max(0, end - time.monotonic()))
        holder.stopped = True
        if holder.ws is not None:
            await holder.ws.close()
        await asyncio.wait_for(holding, 30)
        log("done", connections=[{k: c[k] for k in ("t", "held_s", "code", "ours")} for c in holder.connections])


if __name__ == "__main__":
    asyncio.run(main())
