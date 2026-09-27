"""The dev file source (spec section 14, Ground rules): `carl dev-send <file>`.

A local-only development aid: it sends an audio file over the WebSocket in
place of the microphone, as the page would. It is not the replay and scoring
harness.

It unlocks the local Carl with an access pass, opens `/api/ws` from Carl's
own origin, starts a session and sends the audio as 100 ms binary frames of
16 kHz 16-bit mono PCM, in real time unless `--speed` says otherwise. A
16-bit PCM WAV file is read and converted here; anything else goes through
ffmpeg.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import shutil
import subprocess
import sys
import wave
import zoneinfo
from array import array
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import aiohttp
from yarl import URL

from .gate import COOKIE
from .recording import stamp

RATE = 16000
BYTES_PER_S = RATE * 2
CHUNK_BYTES = 3200  # 100 ms, as the page sends it
CHUNK_S = CHUNK_BYTES / BYTES_PER_S
HEARTBEAT_S = 3.0  # until the server's hello says otherwise
PAUSE_S = 2.0  # how long `--pause-at` stays paused, at real time
TIMEOUT_S = 30.0  # for each reply from the server
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
PASSES_FILE = Path(__file__).resolve().parents[2] / ".secrets.access-passes.txt"


class DevSendError(Exception):
    pass


def add_parser(sub: argparse._SubParsersAction) -> None:
    send = sub.add_parser("dev-send", help="send an audio file to a local Carl as if from the microphone")
    send.add_argument("file", type=Path, help="a WAV file, or any audio ffmpeg reads")
    send.add_argument("--url", default="http://127.0.0.1:8080", help="the local Carl (default: %(default)s)")
    send.add_argument(
        "--pass", dest="password", help="an access pass (default: the first in .secrets.access-passes.txt)"
    )
    send.add_argument("--record", action="store_true", help="start a recording session")
    send.add_argument("--speed", type=positive, default=1.0, help="1 sends in real time, 10 ten times faster")
    send.add_argument("--pause-at", type=float, metavar="SECONDS", help="Pause this far into the file, then resume")
    send.set_defaults(run=run)


def positive(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError("must be more than 0")
    return value


def run(args: argparse.Namespace) -> int:
    try:
        local_origin(args.url)
        password = args.password or first_pass()
        if not password:
            raise DevSendError(f"give an access pass with --pass: {PASSES_FILE.name} has none")
        pcm = load_pcm(args.file)
        seconds = len(pcm) / BYTES_PER_S
        if args.pause_at is not None and not 0 <= args.pause_at < seconds:
            raise DevSendError(f"--pause-at must be within the file's {seconds:.1f} s")
        print(f"{args.file.name}: {seconds:.1f} s of audio to {args.url} at {args.speed:g}x")
        asyncio.run(dev_send(pcm, args.file.name, args.url, password,
                             record=args.record, speed=args.speed, pause_at=args.pause_at))
    except DevSendError as e:
        print(f"carl dev-send: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    return 0


def local_origin(url: str) -> URL:
    """The URL's origin, refusing any Carl that isn't on this machine."""
    parsed = URL(url)
    if parsed.scheme not in ("http", "https") or parsed.host not in LOCAL_HOSTS:
        raise DevSendError(f"{url}: dev-send only talks to a local Carl (http://localhost, 127.0.0.1 or [::1])")
    return parsed.origin()


def first_pass(path: Path | None = None) -> str | None:
    """The first access pass in the owner's local list of `label: pass` lines."""
    try:
        lines = (path or PASSES_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        _, colon, password = line.partition(":")
        if colon and not line.lstrip().startswith("#") and password.strip():
            return password.strip()
    return None


def local_timezone() -> str:
    """The system's IANA time zone, as the page reads it from `Intl`, or UTC."""
    for name in (os.environ.get("TZ", "").lstrip(":"), os.path.realpath("/etc/localtime")):
        name = name.rpartition("zoneinfo/")[2]
        with contextlib.suppress(ValueError, OSError, zoneinfo.ZoneInfoNotFoundError):
            if name and zoneinfo.ZoneInfo(name):
                return name
    return "UTC"


# --- The audio ------------------------------------------------------------------------


def load_pcm(path: Path) -> bytes:
    """The file's audio as 16 kHz 16-bit little-endian mono PCM."""
    if not path.is_file():
        raise DevSendError(f"{path}: no such file")
    pcm = read_wav(path)
    if pcm is None:
        pcm = convert(path)
    if not pcm:
        raise DevSendError(f"{path.name} holds no audio")
    return pcm


def read_wav(path: Path) -> bytes | None:
    """A 16-bit PCM WAV file's audio, downmixed and resampled; None for any other file."""
    try:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                return None
            channels, rate = w.getnchannels(), w.getframerate()
            frames = w.readframes(w.getnframes())
    except (wave.Error, EOFError):
        return None
    frames = frames[: len(frames) - len(frames) % (2 * channels)]
    if channels == 1 and rate == RATE and sys.byteorder == "little":
        return frames
    samples = array("h", frames)
    if sys.byteorder == "big":
        samples.byteswap()
    out = array("h", resample(downmix(samples, channels), rate))
    if sys.byteorder == "big":
        out.byteswap()
    return out.tobytes()


def downmix(samples: Sequence[int], channels: int) -> Sequence[int]:
    """Interleaved samples as mono: each frame's channels averaged."""
    if channels == 1:
        return samples
    return [(sum(frame) + channels // 2) // channels for frame in zip(*(samples[c::channels] for c in range(channels)))]


def resample(samples: Sequence[int], rate: int, to: int = RATE) -> Sequence[int]:
    """Mono samples at `rate` as samples at `to`, by linear interpolation.

    No low-pass filter goes first, so downsampling folds anything above
    `to / 2` back in: fine for speech in a development aid. Integer maths
    throughout, so a long file doesn't drift.
    """
    if rate == to or not samples:
        return samples
    last = len(samples) - 1
    out = []
    for j in range(len(samples) * to // rate):
        i, r = divmod(j * rate, to)
        a, b = samples[i], samples[min(i + 1, last)]
        out.append((a * (to - r) + b * r + to // 2) // to)
    return out


def convert(path: Path) -> bytes:
    """Any audio ffmpeg reads, as 16 kHz mono PCM."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise DevSendError(f"{path.name} isn't a 16-bit PCM WAV file, and converting it needs ffmpeg on PATH")
    done = subprocess.run(
        [ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
        capture_output=True,
    )
    if done.returncode != 0:
        detail = (done.stderr.decode(errors="replace").strip().splitlines() or ["no reason given"])[-1]
        raise DevSendError(f"ffmpeg couldn't convert {path.name}: {detail}")
    return done.stdout


# --- The page's side of the WebSocket -------------------------------------------------


async def dev_send(pcm: bytes, name: str, url: str, password: str, *,
                   record: bool = False, speed: float = 1.0, pause_at: float | None = None) -> dict[str, Any]:
    """Send `pcm` to the local Carl at `url` as the page would; the `ended` message."""
    origin = local_origin(url)
    timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=TIMEOUT_S)
    try:
        async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True), timeout=timeout) as http:
            await unlock(http, origin, password)
            async with http.ws_connect(origin.with_path("/api/ws"), origin=str(origin)) as ws:
                page = Page(ws)
                reader = asyncio.create_task(page.read())
                try:
                    return await page.session(pcm, name, record, speed, pause_at)
                finally:
                    reader.cancel()
    except aiohttp.ClientConnectorError as e:
        raise DevSendError(f"can't reach Carl at {origin}: is `carl serve` running? ({e.os_error})") from e
    except (aiohttp.ClientError, ConnectionError) as e:
        raise DevSendError(f"the connection to Carl failed: {e}") from e


async def unlock(http: aiohttp.ClientSession, origin: URL, password: str) -> None:
    async with http.post(origin.with_path("/api/unlock"), data={"pass": password}, allow_redirects=False) as response:
        token = response.cookies.get(COOKIE)
        if response.status != 303 or token is None:
            raise DevSendError(f"Carl at {origin} didn't take the access pass (HTTP {response.status})")
    # The cookie is Secure, and a local Carl is plain http, so it goes into
    # the jar by hand.
    http.cookie_jar.update_cookies({COOKIE: token.value}, origin)


class Page:
    """One run's WebSocket, driven the way the page drives it."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self.ws = ws
        self.loop = asyncio.get_running_loop()
        self.last_sent = self.loop.time()
        self.heartbeat_s = HEARTBEAT_S
        self.messages: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.dotted = False

    def say(self, text: str) -> None:
        if self.dotted:
            print()
            self.dotted = False
        print(text, flush=True)

    async def send(self, message: dict[str, Any]) -> None:
        await self.ws.send_str(json.dumps(message, ensure_ascii=False))
        self.last_sent = self.loop.time()

    async def keep_alive(self) -> None:
        """A heartbeat whenever nothing else went for `heartbeat_s`."""
        while not self.ws.closed:
            wait = self.last_sent + self.heartbeat_s - self.loop.time()
            if wait > 0:
                await asyncio.sleep(wait)
                continue
            try:
                await self.send({"type": "heartbeat"})
            except ConnectionError:
                return  # closing: `read` and the sender see it too

    async def read(self) -> None:
        """Pulse a dot for each `speech`, and queue every other message but heartbeats."""
        async for frame in self.ws:
            if frame.type is not aiohttp.WSMsgType.TEXT:
                continue
            with contextlib.suppress(ValueError, AttributeError):
                message = json.loads(frame.data)
                if message.get("type") == "speech":
                    print(".", end="", flush=True)
                    self.dotted = True
                elif message.get("type") != "heartbeat":
                    self.messages.put_nowait(message)
        self.messages.put_nowait(None)

    async def expect(self, kind: str) -> dict[str, Any]:
        while True:
            try:
                message = await asyncio.wait_for(self.messages.get(), TIMEOUT_S)
            except TimeoutError:
                raise DevSendError(f"no {kind!r} message from Carl within {TIMEOUT_S:.0f} s") from None
            if message is None:
                raise DevSendError(f"Carl closed the connection (code {self.ws.close_code}) before {kind!r}")
            if message.get("type") == kind:
                return message
            if message.get("type") == "ended":
                raise DevSendError(f"the session ended early: {message.get('summary')}")

    async def session(self, pcm: bytes, name: str, record: bool, speed: float,
                      pause_at: float | None) -> dict[str, Any]:
        """Hello, then the heartbeat at the rate it names, then the session."""
        hello = await self.expect("hello")
        self.heartbeat_s = float(hello.get("config", {}).get("connection", {}).get("heartbeat_s", HEARTBEAT_S))
        keep_alive = asyncio.create_task(self.keep_alive())
        try:
            return await self.send_file(pcm, name, record, speed, pause_at)
        finally:
            keep_alive.cancel()

    async def send_file(self, pcm: bytes, name: str, record: bool, speed: float,
                        pause_at: float | None) -> dict[str, Any]:
        disclosure = {"text": f"dev-send: {name}", "confirmed_at": stamp()} if record else None
        await self.send({"type": "start", "record": record, "disclosure": disclosure,
                         "mic": {"source": "dev-send", "file": name}, "timezone": local_timezone()})
        state = await self.expect("session")
        self.say(f"session {state['session']} started, {'recording' if state.get('recording') else 'not recording'}")
        try:
            await self.play(pcm, speed, pause_at)
        except asyncio.CancelledError:  # Ctrl-C: end it rather than leave it to its grace period
            with contextlib.suppress(ConnectionError):
                await self.send({"type": "end"})
            raise
        await self.send({"type": "end"})
        ended = await self.expect("ended")
        summary = ended.get("summary") or {}
        self.say(f"session {ended.get('session')} ended: " + ", ".join(f"{k} {v}" for k, v in summary.items()))
        return ended

    async def play(self, pcm: bytes, speed: float, pause_at: float | None) -> None:
        """The audio in 100 ms frames, one every 100 ms / `speed`, pausing once at `pause_at`."""
        due = self.loop.time()
        for offset in range(0, len(pcm), CHUNK_BYTES):
            if pause_at is not None and offset >= pause_at * BYTES_PER_S:
                pause_at = None
                await self.pause(PAUSE_S / speed)
                due = self.loop.time()
            await asyncio.sleep(max(0.0, due - self.loop.time()))
            await self.ws.send_bytes(pcm[offset : offset + CHUNK_BYTES])
            self.last_sent = self.loop.time()
            due += CHUNK_S / speed

    async def pause(self, seconds: float) -> None:
        await self.send({"type": "pause"})
        self.say(f"paused: {(await self.expect('session'))['state']}")
        await asyncio.sleep(seconds)
        await self.send({"type": "resume"})
        self.say(f"resumed: {(await self.expect('session'))['state']}")
