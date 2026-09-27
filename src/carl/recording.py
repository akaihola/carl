"""A recording session's recording (spec section 9, What a recording keeps).

Everything goes under `recordings/<id>/` in the store while the session
runs, not at End:

- `audio/<n>.pcm`: raw 16 kHz 16-bit mono PCM exactly as sent to
  speech-to-text, in objects of about one minute. An object ends early at a
  break in the audio (Pause, a dropped connection), so each holds one
  unbroken stretch; an `audio` event in the log says where it starts.
- `events/<n>.jsonl`: the event log, one JSON object per line with
  `time` (ISO 8601 UTC) and `event`, written as a new part about every 10 s,
  so a crash loses at most one audio object's tail and a few seconds of log.

A write that fails stays queued and is tried again, under the same key, at
the next flush. The stop (Stopping a recording) waits for any write already
under way, so none can land after the delete.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from .storage import Store

log = logging.getLogger(__name__)

AUDIO_OBJECT_BYTES = 16000 * 2 * 60  # about one minute
FLUSH_S = 10.0
# `close` tries this many times, RETRY_S apart, before giving up on a write.
CLOSE_TRIES = 3
RETRY_S = 1.0


def stamp() -> str:
    """Now, in ISO 8601 UTC with milliseconds: `2026-09-27T18:02:11.123Z`."""
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Recorder:
    def __init__(self, store: Store, session_id: str) -> None:
        if not session_id or "/" in session_id:
            raise ValueError(f"not a session id: {session_id!r}")
        self.store, self.session_id = store, session_id
        self._events: list[str] = []  # JSON lines not yet written
        self._part = 1  # the next events part
        self._audio = bytearray()  # the audio object being filled
        self._audio_start = ""
        self._objects: deque[tuple[str, bytes]] = deque()  # ended audio objects not yet written
        self._object = 1  # the next audio object
        self._lock = asyncio.Lock()  # one flush at a time
        self._writes: set[asyncio.Task[None]] = set()  # puts under way
        self._ended = asyncio.Event()
        self._closed = self._stopped = False
        self.failing = False  # the last write failed: nothing reaches storage for now
        self.on_failing: Callable[[], None] | None = None  # told when `failing` changes

    @property
    def prefix(self) -> str:
        """`recordings/<id>/`."""
        return f"recordings/{self.session_id}/"

    @property
    def active(self) -> bool:
        """True until `stop_and_delete` or `close`."""
        return not (self._closed or self._stopped)

    def log(self, event: str, **fields: Any) -> None:
        """Queue an event for the log. Ignored once stopped."""
        if "time" in fields:
            raise ValueError("`time` is the time the event was logged")
        if self.active:
            self._queue(event, fields)

    def audio(self, chunk: bytes) -> None:
        """Queue audio exactly as sent to speech-to-text. Ignored once stopped."""
        if not self.active or not chunk:
            return
        if not self._audio:
            self._audio_start = stamp()
        self._audio += chunk
        if len(self._audio) >= AUDIO_OBJECT_BYTES:
            self._end_object()

    def audio_break(self) -> None:
        """The audio stops here (Pause, a drop): end the current audio object."""
        if self.active:
            self._end_object()

    async def flush(self) -> None:
        """Write the queued events as a new part, and any full or ended audio object."""
        async with self._lock:
            if self._writes:  # left under way by a flush that was cancelled
                await asyncio.wait(set(self._writes))
            while self._objects:
                key, data = self._objects[0]
                if not await self._put(key, data):
                    break  # the rest wait, in order
                self._objects.popleft()
            if self._events:
                count = len(self._events)
                if await self._put(f"events/{self._part:06d}.jsonl", "".join(self._events[:count]).encode()):
                    del self._events[:count]
                    self._part += 1

    async def run(self) -> None:
        """Flush every FLUSH_S until closed or stopped. Run it as a task."""
        while self.active:
            try:
                await asyncio.wait_for(self._ended.wait(), FLUSH_S)
            except TimeoutError:
                await self.flush()

    async def close(self) -> None:
        """Write everything still queued, and stop."""
        self._closed = True
        self._ended.set()
        self._end_object()
        for attempt in range(CLOSE_TRIES):
            if attempt:
                await asyncio.sleep(RETRY_S)
            await self.flush()
            if not (self._events or self._objects):
                return
        log.error("recording %s: %d events and %d audio objects could not be written",
                  self.session_id, len(self._events), len(self._objects))

    async def stop_and_delete(self) -> int:
        """The one-way stop: delete all of `recordings/<id>/` at once and keep
        nothing more. Returns how many objects were deleted."""
        self._stopped = True
        self._ended.set()
        self._events.clear()
        self._audio = bytearray()
        self._objects.clear()
        # A put can't be called back once sent, so wait for it rather than
        # let it land after the delete.
        if self._writes:
            await asyncio.wait(set(self._writes))
        deleted = await self.store.delete_prefix(self.prefix)
        log.info("recording %s stopped: %d objects deleted", self.session_id, deleted)
        return deleted

    def _queue(self, event: str, fields: dict[str, Any]) -> None:
        line = json.dumps({"time": stamp(), "event": event, **fields}, ensure_ascii=False, default=str)
        self._events.append(line + "\n")

    def _end_object(self) -> None:
        if not self._audio:
            return
        key = f"audio/{self._object:06d}.pcm"
        self._objects.append((key, bytes(self._audio)))
        self._queue("audio", {"key": key, "start": self._audio_start, "bytes": len(self._audio)})
        self._object += 1
        self._audio = bytearray()

    async def _put(self, key: str, data: bytes) -> bool:
        """Write one object under the prefix. False if it failed, so it stays
        queued, or if the recording was stopped meanwhile.

        The put runs as its own task, shielded, so cancelling a flush leaves it
        to finish; the stop and the next flush wait for it.
        """
        if self._stopped:
            return False
        task = asyncio.create_task(self.store.put(self.prefix + key, data))
        self._writes.add(task)
        task.add_done_callback(self._written)
        try:
            await asyncio.shield(task)
        except Exception:
            log.warning("recording %s: writing %s failed; it stays queued", self.session_id, key, exc_info=True)
            self._failing(True)
            return False
        self._failing(False)
        return not self._stopped

    def _failing(self, failing: bool) -> None:
        if failing != self.failing:
            self.failing = failing
            if self.on_failing is not None:
                self.on_failing()

    def _written(self, task: asyncio.Task[None]) -> None:
        self._writes.discard(task)
        if not task.cancelled():
            task.exception()  # seen here, so a failure after a cancelled flush raises no asyncio warning
