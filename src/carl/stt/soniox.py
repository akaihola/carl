"""The Soniox adapter: stt-rt-v5 over Soniox's real-time WebSocket API.

The protocol (https://soniox.com/docs/api-reference/stt/websocket-api):

- The first frame is the JSON config, with the API key in it. Audio follows
  as binary frames. An empty frame ends the stream: Soniox answers with its
  last tokens and `finished: true`, then closes.
- `{"type": "keepalive"}` keeps a stream open while no audio flows; Soniox
  closes one that hears nothing for 20 s. `{"type": "finalize"}` makes every
  token heard so far final and ends with a final `<fin>` token.
- Each response carries sub-word tokens: the new final ones, sent once and
  never changed, then all the current non-final ones, which the next
  response replaces. With endpoint detection, a final `<end>` token closes a
  segment no later than `max_endpoint_delay_ms` after speech ends.
- An error is one JSON frame with `error_code` (an HTTP status) and
  `error_type`, after which Soniox closes the connection. It comes out as a
  last event, carrying any final words still held, then as an SttError.
- Soniox answers WebSocket pings, so a dead connection shows up within
  HEARTBEAT_S plus half that, as a timeout.

Tokens become words in `Joiner`. `<end>` and `<fin>` are markers, not words,
and both set the event's `endpoint`: after either, every final word so far
belongs to a finished segment, which is all the pipeline needs to know.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Iterable
from typing import Any

import aiohttp

from ..config import Stage
from . import SAMPLE_RATE, SttError, SttEvent, Word

URL = "wss://stt-rt.soniox.com/transcribe-websocket"
# Soniox's name for AUDIO_FORMAT, raw 16-bit little-endian PCM.
AUDIO_FORMAT = "pcm_s16le"
MARKERS = frozenset({"<end>", "<fin>"})
OPEN_TIMEOUT_S = 10
# A WebSocket ping goes out after this long without a frame from Soniox, and
# a missing pong ends the stream with a timeout.
HEARTBEAT_S = 10
# How long after close() Soniox has to send `finished`.
CLOSE_TIMEOUT_S = 10

RATE_LIMITED = frozenset({
    "limit_exceeded",
    "organization_balance_exhausted",
    "organization_monthly_budget_exhausted",
    "project_monthly_budget_exhausted",
})

Token = dict[str, Any]


class Soniox:
    """Speech-to-text by Soniox, as `stages.speech_to_text` configures it."""

    def __init__(self, stage: Stage, api_key: str, url: str = URL):
        self.stage, self.api_key, self.url = stage, api_key, url

    def request(self, languages: list[str]) -> dict[str, Any]:
        """The config frame that starts a stream. The stage's params may
        override the defaults but not the model or the audio format."""
        return {
            "language_hints": list(languages),
            "enable_speaker_diarization": True,
            "enable_language_identification": True,
            **self.stage.params,
            "api_key": self.api_key,
            "model": self.stage.model,
            "audio_format": AUDIO_FORMAT,
            "sample_rate": SAMPLE_RATE,
            "num_channels": 1,
        }

    async def open(self, languages: list[str]) -> SonioxStream:
        http = aiohttp.ClientSession(trust_env=True)
        try:
            async with asyncio.timeout(OPEN_TIMEOUT_S):
                ws = await http.ws_connect(self.url, heartbeat=HEARTBEAT_S)
                await ws.send_str(json.dumps(self.request(languages)))
        except BaseException as e:
            await http.close()
            if isinstance(e, TimeoutError):
                raise SttError("timeout", f"no connection to Soniox in {OPEN_TIMEOUT_S} s") from e
            if isinstance(e, aiohttp.WSServerHandshakeError):
                kind = "rate-limited" if e.status == 429 else "unavailable"
                raise SttError(kind, f"HTTP {e.status} on connecting") from e
            if isinstance(e, (aiohttp.ClientError, OSError)):
                raise SttError("unavailable", f"can't connect: {e!r}") from e
            raise
        return SonioxStream(http, ws)


class SonioxStream:
    """One open Soniox stream. It never retries: the pipeline decides."""

    def __init__(self, http: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse):
        self.http, self.ws = http, ws
        self.joiner = Joiner()
        self.closing = False
        self.timed_out = False
        self.watchdog: asyncio.Task | None = None

    async def send_audio(self, chunk: bytes) -> None:
        if chunk:  # an empty frame would end the stream
            await self.send(chunk)

    async def keepalive(self) -> None:
        await self.send(json.dumps({"type": "keepalive"}))

    async def finalize(self) -> None:
        await self.send(json.dumps({"type": "finalize"}))

    async def close(self) -> None:
        """Ask Soniox to finish. `events()` ends once it has, or fails after
        CLOSE_TIMEOUT_S. Never raises."""
        if self.closing:
            return
        with contextlib.suppress(SttError):
            await self.send("")
        self.closing = True
        if not self.ws.closed:
            self.watchdog = asyncio.create_task(self.give_up_after(CLOSE_TIMEOUT_S))

    async def send(self, data: str | bytes) -> None:
        if self.closing or self.ws.closed:
            raise SttError("unavailable", "the stream is closed")
        try:
            if isinstance(data, bytes):
                await self.ws.send_bytes(data)
            else:
                await self.ws.send_str(data)
        except (ConnectionError, aiohttp.ClientError) as e:
            raise SttError("unavailable", f"can't send: {e!r}") from e

    async def events(self) -> AsyncIterator[SttEvent]:
        try:
            while True:
                message = await self.ws.receive()
                if message.type is aiohttp.WSMsgType.TEXT:
                    event, error = self.parse(message.data)
                    if event.finished or error:
                        await self.release()
                    yield event
                    if error:
                        raise error
                    if event.finished:
                        return
                elif message.type is aiohttp.WSMsgType.BINARY:
                    raise SttError("bad output", "a binary frame from Soniox")
                else:
                    raise self.dropped(message)
        finally:
            await self.release()

    def parse(self, data: str) -> tuple[SttEvent, SttError | None]:
        """One response as an event, and the error it reports, if any."""
        try:
            message = json.loads(data)
        except ValueError:
            raise SttError("bad output", f"not JSON: {data[:200]!r}") from None
        if not isinstance(message, dict):
            raise SttError("bad output", f"not a JSON object: {data[:200]!r}")
        if "error_code" in message or "error_type" in message:
            words, endpoint = self.joiner.feed([], finished=True)
            return SttEvent(words=tuple(words), endpoint=endpoint, raw=message), error(message)
        finished = message.get("finished") is True
        words, endpoint = self.joiner.feed(tokens(message), finished)
        return SttEvent(words=tuple(words), endpoint=endpoint, finished=finished, raw=message), None

    def dropped(self, message: aiohttp.WSMessage) -> SttError:
        if self.timed_out:
            return SttError("timeout", f"no `finished` from Soniox {CLOSE_TIMEOUT_S} s after closing")
        cause = message.data if message.type is aiohttp.WSMsgType.ERROR else self.ws.exception()
        if isinstance(cause, aiohttp.ServerTimeoutError):
            return SttError("timeout", str(cause))
        return SttError("unavailable", f"connection closed (code {self.ws.close_code}, {cause!r})")

    async def give_up_after(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        self.watchdog = None
        self.timed_out = not self.ws.closed
        await self.release()

    async def release(self) -> None:
        """Close the socket and its HTTP session. Safe to call again."""
        if self.watchdog is not None:
            self.watchdog.cancel()
            self.watchdog = None
        with contextlib.suppress(Exception):
            await self.ws.close()
        await self.http.close()


def tokens(message: dict[str, Any]) -> list[Token]:
    """The response's tokens, checked for what the joiner relies on."""
    found = message.get("tokens", [])
    if not isinstance(found, list):
        raise SttError("bad output", "`tokens` is not a list")
    for token in found:
        if not (isinstance(token, dict) and isinstance(token.get("text"), str) and isinstance(token.get("is_final"), bool)):
            raise SttError("bad output", f"a malformed token: {token!r}")
        if token["text"] not in MARKERS and not all(isinstance(token.get(k), int | float) for k in ("start_ms", "end_ms")):
            raise SttError("bad output", f"a token without times: {token!r}")
    return found


def error(message: dict[str, Any]) -> SttError:
    """Soniox's error frame as a typed error. Branch on `error_type`, as
    Soniox asks, with the HTTP status as a fallback."""
    code, kind_name = message.get("error_code"), message.get("error_type")
    if kind_name in RATE_LIMITED or code in (402, 429):
        kind = "rate-limited"
    elif kind_name == "request_timeout" or code == 408:
        kind = "timeout"
    else:
        kind = "unavailable"
    detail = f"{code} {kind_name}: {message.get('error_message', '')} (request {message.get('request_id')})"
    return SttError(kind, detail)


class Joiner:
    """Joins one stream's sub-word tokens into words.

    A token starting with whitespace starts a word and one ending with it
    ends its word; any other token, punctuation included, carries on the
    word before it. A marker also ends a word. A change of speaker or
    language doesn't: Soniox starts every new word with a space, and its
    speaker label can flip inside a word ("F", "inn" by speaker 3, then
    "ish" by speaker 2, in a live check). A word takes its first token's
    speaker and language.

    Soniox can finalise a word in parts, so a word is only final once a
    later final token or a marker shows that it has ended. Until then its
    final tokens are held back and shown within an interim word. That way no
    final word comes out twice or cut short. Final tokens after a marker are
    held for the next response too, so that an event's `endpoint` covers
    exactly the final words in it and those before.
    """

    def __init__(self) -> None:
        self.held: list[Token] = []

    def feed(self, tokens: list[Token], finished: bool = False) -> tuple[list[Word], bool]:
        """One response's tokens in; its final words, then its interim words,
        and whether a marker ended a segment. `finished` flushes all."""
        finals = self.held + [t for t in tokens if t["is_final"]]
        interim = [t for t in tokens if not t["is_final"]]
        marker = next((i for i, t in enumerate(finals) if t["text"] in MARKERS), None)
        if finished:
            done, self.held = whole(group(finals)), []
        elif marker is not None:
            done, self.held = whole(group(finals[:marker])), finals[marker + 1:]
        else:
            done, self.held = group(finals)
        words = [word(w, True) for w in done] + [word(w, False) for w in whole(group(self.held + interim))]
        return words, marker is not None


def group(tokens: Iterable[Token]) -> tuple[list[list[Token]], list[Token]]:
    """Tokens split into words: the ended ones, and the last one's tokens if
    nothing has ended it yet."""
    ended: list[list[Token]] = []
    current: list[Token] = []
    for token in tokens:
        text = token["text"]
        if text in MARKERS or text[:1].isspace():
            if current:
                ended.append(current)
            current = []
        if text in MARKERS or not text.strip():
            continue
        current.append(token)
        if text[-1].isspace():
            ended.append(current)
            current = []
    return ended, current


def whole(split: tuple[list[list[Token]], list[Token]]) -> list[list[Token]]:
    ended, last = split
    return ended + [last] if last else ended


def word(tokens: list[Token], final: bool) -> Word:
    first = tokens[0]
    return Word(
        text="".join(t["text"] for t in tokens).strip(),
        start_ms=int(first["start_ms"]),
        end_ms=int(tokens[-1]["end_ms"]),
        speaker=str(first.get("speaker") or ""),
        language=str(first.get("language") or ""),
        final=final,
    )
