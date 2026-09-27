import socket

import aiohttp
import pytest


def test_tests_cannot_reach_a_provider():
    with pytest.raises(ConnectionRefusedError, match="tests make no network calls"), socket.socket() as s:
        s.connect(("162.159.140.245", 443))


async def test_not_through_aiohttp_either():
    async with aiohttp.ClientSession() as session:
        with pytest.raises(aiohttp.ClientConnectionError):
            await session.get("https://1.1.1.1/", timeout=aiohttp.ClientTimeout(total=5))
