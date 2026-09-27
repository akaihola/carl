from __future__ import annotations

import dataclasses
import ipaddress
import socket
from pathlib import Path

import pytest

from carl.config import Config, load_config
from carl.gate import COOKIE, Passes, hash_password
from carl.server import create_app

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "bakodi-sulema-rotike-fanupa"
OTHER_PASSWORD = "kivuna-demosa-lopati-rukeba"
TOKEN_SECRET = "x" * 40


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No live provider calls: only connections to this machine are allowed."""
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


def quick(config: Config, heartbeat_s: float = 0.05, silence_s: float = 0.3) -> Config:
    """The config with a heartbeat fast enough for a test."""
    connection = dataclasses.replace(config.connection, heartbeat_s=heartbeat_s, silence_s=silence_s)
    return dataclasses.replace(config, connection=connection)


@pytest.fixture
async def client(aiohttp_client, config, passes):
    return await aiohttp_client(create_app(quick(config), {}, passes))


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
