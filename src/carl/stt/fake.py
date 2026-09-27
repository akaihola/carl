"""A fake speech-to-text for tests: streams that play scripted events.

Each stream plays its script, then whatever a test adds with `say`, `push`
or `fail`. It keeps the audio it was sent and counts keepalives. Finalize
adds an endpoint event and close adds the `finished` event, as a real
provider would, so a pipeline test sees the same order of events.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import Literal

from . import SttError, SttEvent, Word


def words(speaker: str, text: str, start_ms: int = 0, language: str = "fi", final: bool = True) -> tuple[Word, ...]:
    """The text's words, one every 400 ms from `start_ms`, each 300 ms long."""
    return tuple(
        Word(w, start_ms + 400 * i, start_ms + 400 * i + 300, speaker, language, final)
        for i, w in enumerate(text.split())
    )


class FakeStream:
    def __init__(self, languages: list[str], script: Iterable[SttEvent | SttError] = ()):
        self.languages = languages
        self.audio = bytearray()
        self.keepalives = self.finalized = 0
        self.closed = False
        self.queue: asyncio.Queue[SttEvent | SttError] = asyncio.Queue()
        for item in script:
            self.push(item)

    def push(self, item: SttEvent | SttError) -> None:
        """Play this event next, or raise this error from `events()`."""
        self.queue.put_nowait(item)

    def say(self, speaker: str, text: str, start_ms: int = 0, language: str = "fi", endpoint: bool = True) -> None:
        """Play one segment of final words."""
        self.push(SttEvent(words(speaker, text, start_ms, language), endpoint=endpoint, raw={"said": text}))

    def fail(self, kind: Literal["timeout", "unavailable", "rate-limited", "bad output"], detail: str = "") -> None:
        self.push(SttError(kind, detail))

    async def send_audio(self, chunk: bytes) -> None:
        if self.closed:
            raise SttError("unavailable", "the stream is closed")
        self.audio += chunk

    async def keepalive(self) -> None:
        self.keepalives += 1

    async def finalize(self) -> None:
        self.finalized += 1
        self.push(SttEvent(endpoint=True, raw={"fake": "finalized"}))

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.push(SttEvent(endpoint=True, finished=True, raw={"fake": "finished"}))

    async def events(self) -> AsyncIterator[SttEvent]:
        while True:
            item = await self.queue.get()
            if isinstance(item, SttError):
                raise item
            yield item
            if item.finished:
                return


class FakeSpeechToText:
    """Opens FakeStreams, the n-th one playing the n-th script. While
    `open_error` is set, `open` raises it instead."""

    def __init__(self, *scripts: Iterable[SttEvent | SttError]):
        self.scripts = list(scripts)
        self.streams: list[FakeStream] = []
        self.open_error: SttError | None = None

    async def open(self, languages: list[str]) -> FakeStream:
        if self.open_error is not None:
            raise self.open_error
        script = self.scripts[len(self.streams)] if len(self.streams) < len(self.scripts) else ()
        self.streams.append(FakeStream(languages, script))
        return self.streams[-1]
