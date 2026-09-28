from __future__ import annotations

import asyncio
import dataclasses
import ipaddress
import socket
from pathlib import Path

import pytest

from carl.config import Config, load_config
from carl.gate import COOKIE, Passes, hash_password
from carl.server import create_app
from carl.session import Sessions
from carl.storage import MemoryStore
from carl.stt import SttEvent, Word

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "bakodi-sulema-rotike-fanupa"
OTHER_PASSWORD = "kivuna-demosa-lopati-rukeba"
TOKEN_SECRET = "x" * 40


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No live provider calls: only connections to this machine are allowed.

    The proxy variables go too, since a proxy on this machine could carry a
    request out.
    """
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "WSS_PROXY", "WS_PROXY", "ALL_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    real_connect = socket.socket.connect

    def connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0]
            if host != "localhost" and not ipaddress.ip_address(host).is_loopback:
                raise ConnectionRefusedError(f"tests make no network calls, not even to {host}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", connect)


@pytest.fixture(scope="session")
def config() -> Config:
    return load_config(ROOT / "config.toml")


@pytest.fixture(scope="session")
def entries() -> str:
    return f"{hash_password(PASSWORD)},{hash_password(OTHER_PASSWORD)}"


@pytest.fixture
def passes(entries) -> Passes:
    return Passes(entries, TOKEN_SECRET)


def quick(config: Config, heartbeat_s: float = 0.05, silence_s: float = 0.3, grace_s: float = 120) -> Config:
    """The config with a heartbeat fast enough for a test."""
    connection = dataclasses.replace(
        config.connection, heartbeat_s=heartbeat_s, silence_s=silence_s, reconnect_grace_s=grace_s
    )
    return dataclasses.replace(config, connection=connection)


class ScriptedStream:
    """A speech-to-text stream that says what a test tells it to."""

    def __init__(self) -> None:
        self.audio = bytearray()
        self.queue: asyncio.Queue[SttEvent] = asyncio.Queue()
        self.finalized = self.keepalives = 0
        self.closed = False

    async def send_audio(self, chunk: bytes) -> None:
        self.audio += chunk

    async def keepalive(self) -> None:
        self.keepalives += 1

    async def finalize(self) -> None:
        self.finalized += 1
        await self.queue.put(SttEvent(endpoint=True, raw={"finalized": True}))

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(SttEvent(finished=True, raw={"finished": True}))

    async def events(self):
        while True:
            event = await self.queue.get()
            yield event
            if event.finished:
                return

    def say(self, speaker: str, text: str, start_ms: int = 0, endpoint: bool = True, language: str = "fi") -> None:
        words = tuple(
            Word(w, start_ms + 400 * i, start_ms + 400 * i + 300, speaker, language, True)
            for i, w in enumerate(text.split())
        )
        self.queue.put_nowait(SttEvent(words=words, endpoint=endpoint, raw={"said": text}))


class ScriptedStt:
    def __init__(self) -> None:
        self.streams: list[ScriptedStream] = []

    async def open(self, languages: list[str]) -> ScriptedStream:
        self.streams.append(ScriptedStream())
        return self.streams[-1]


class GatedStore(MemoryStore):
    """A bucket that holds every write until the test opens the gate."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = asyncio.Event()
        self.waiting = 0

    async def put(self, key: str, data: bytes) -> None:
        self.waiting += 1
        await self.gate.wait()
        self.waiting -= 1
        await super().put(key, data)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def stt() -> ScriptedStt:
    return ScriptedStt()


@pytest.fixture
def app_config(config) -> Config:
    return quick(config)


@pytest.fixture
async def client(aiohttp_client, app_config, passes, store, stt):
    sessions = Sessions(app_config, {}, store, stt, "test")
    return await aiohttp_client(create_app(app_config, {}, passes, sessions))


@pytest.fixture
async def unlocked(client):
    """A client that has entered the access pass.

    The cookie is Secure, and the test server is plain http, so it is copied
    into the client's cookie jar by hand.
    """
    response = await client.post("/api/unlock", data={"pass": PASSWORD}, allow_redirects=False)
    assert response.status == 303
    client.session.cookie_jar.update_cookies({COOKIE: response.cookies[COOKIE].value})
    return client
