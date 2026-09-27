import asyncio
import json

import aiohttp
import pytest

from carl.link import SILENCE_CLOSE, Link

from .conftest import quick


async def test_the_upgrade_needs_the_access_pass(client):
    with pytest.raises(aiohttp.WSServerHandshakeError) as e:
        await client.ws_connect("/api/ws")
    assert e.value.status == 401


async def test_the_upgrade_needs_carls_own_origin(unlocked):
    with pytest.raises(aiohttp.WSServerHandshakeError) as e:
        await unlocked.ws_connect("/api/ws", origin="https://example.com")
    assert e.value.status == 403
    ws = await unlocked.ws_connect("/api/ws", origin=f"http://{unlocked.host}:{unlocked.port}")
    await ws.close()


async def test_the_page_gets_its_config_at_the_start(unlocked, config):
    ws = await unlocked.ws_connect("/api/ws")
    hello = await ws.receive_json(timeout=1)
    assert hello["type"] == "hello"
    assert hello["config"] == quick(config).page_values()
    assert hello["costs"] == {"month_usd": 0, "month_eur": 0}
    await ws.close()


async def test_the_server_beats_while_idle(unlocked):
    ws = await unlocked.ws_connect("/api/ws")
    await ws.receive_json(timeout=1)
    loop = asyncio.get_running_loop()
    start = loop.time()
    beats = []
    while loop.time() - start < 0.25:
        await ws.send_json({"type": "heartbeat"})
        beats.append(await ws.receive_json(timeout=0.2))
    assert all(b == {"type": "heartbeat"} for b in beats)
    assert 3 <= len(beats) <= 7  # every 0.05 s
    await ws.close()


async def test_silence_drops_the_connection(unlocked):
    ws = await unlocked.ws_connect("/api/ws")
    loop = asyncio.get_running_loop()
    start = loop.time()
    while (message := await ws.receive(timeout=1)).type is aiohttp.WSMsgType.TEXT:
        pass
    assert message.type is aiohttp.WSMsgType.CLOSE
    assert ws.close_code == SILENCE_CLOSE
    assert 0.3 <= loop.time() - start < 1


@pytest.mark.parametrize("keep_alive", [{"type": "heartbeat"}, b"\0" * 3200], ids=["heartbeat", "audio"])
async def test_any_message_keeps_the_connection(unlocked, keep_alive):
    ws = await unlocked.ws_connect("/api/ws")
    for _ in range(12):  # 0.6 s, twice the silence
        await (ws.send_bytes(keep_alive) if isinstance(keep_alive, bytes) else ws.send_json(keep_alive))
        await asyncio.sleep(0.05)
    assert not ws.closed
    await ws.send_str("not json")  # ignored, but alive
    await ws.send_json({"type": "something later"})
    await asyncio.sleep(0.05)
    assert not ws.closed
    await ws.close()


class FakeSocket:
    def __init__(self):
        self.closed = False
        self.sent: list[dict] = []
        self.close_code = None

    async def send_str(self, data):
        self.sent.append(json.loads(data))

    async def close(self, *, code, message):
        self.closed, self.close_code = True, code


async def test_no_heartbeat_while_other_messages_flow():
    ws = FakeSocket()
    link = Link(ws, heartbeat_s=0.05, silence_s=10)
    task = asyncio.create_task(link.keep_alive())
    for n in range(10):
        await link.send({"type": "card", "n": n})
        await asyncio.sleep(0.02)
    assert [m["type"] for m in ws.sent] == ["card"] * 10
    await asyncio.sleep(0.08)
    assert ws.sent[-1] == {"type": "heartbeat"}
    task.cancel()


async def test_the_server_drops_a_silent_page():
    ws = FakeSocket()
    link = Link(ws, heartbeat_s=0.05, silence_s=0.2)
    await asyncio.wait_for(link.keep_alive(), timeout=1)
    assert ws.close_code == SILENCE_CLOSE
    assert link.dropped
    assert {"type": "heartbeat"} in ws.sent


async def test_a_shutdown_lets_the_page_go_at_once(unlocked):
    ws = await unlocked.ws_connect("/api/ws")
    await ws.receive_json(timeout=1)
    await unlocked.server.app.shutdown()
    while (message := await ws.receive(timeout=1)).type is aiohttp.WSMsgType.TEXT:
        pass
    assert message.type is aiohttp.WSMsgType.CLOSE
    assert ws.close_code == aiohttp.WSCloseCode.GOING_AWAY
