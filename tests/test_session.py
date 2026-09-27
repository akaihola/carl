import asyncio
import contextlib
import json

import pytest

from carl.session import SESSION_ID

from .conftest import quick

DISCLOSURE = {"text": "Tämä on testi. …", "confirmed_at": "2026-09-27T18:02:11.123Z"}


async def connect(client):
    ws = await client.ws_connect("/api/ws")
    hello = await ws.receive_json(timeout=1)
    assert hello["type"] == "hello"
    return ws


async def receive(ws, kind, timeout=2):
    """The next message of `kind`, skipping heartbeats, speech pulses, the
    indicator and updates of the recording mark."""
    while True:
        message = await ws.receive_json(timeout=timeout)
        if message["type"] == kind:
            return message
        assert message["type"] in {"heartbeat", "speech", "indicator", "session"}, message


async def start(ws, record=True):
    await ws.send_json({"type": "start", "record": record, "disclosure": DISCLOSURE if record else None,
                        "mic": {"sampleRate": 16000, "autoGainControl": True}, "timezone": "Europe/Helsinki"})
    state = await receive(ws, "session")
    assert SESSION_ID.fullmatch(state["session"])
    return state


async def events(store, session_id):
    lines = []
    for key in await store.list(f"recordings/{session_id}/events/"):
        lines += [json.loads(line) for line in (await store.get(key)).decode().splitlines()]
    return lines


async def settle():
    for _ in range(5):
        await asyncio.sleep(0.02)


async def test_a_recording_session_from_start_to_end(unlocked, stt, store):
    ws = await connect(unlocked)
    state = await start(ws)
    assert state["state"] == "listening" and state["recording"]
    session_id = state["session"]
    for _ in range(10):
        await ws.send_bytes(b"\1\0" * 1600)
    await settle()
    stream = stt.streams[0]
    assert bytes(stream.audio) == b"\1\0" * 16000
    stream.say("1", "Einstein reputtasi matematiikassa.")
    assert (await receive(ws, "speech"))["type"] == "speech"
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    assert ended["session"] == session_id
    summary = ended["summary"]
    assert summary["recording"] == "kept" and summary["cards"] is None
    assert summary["listening_s"] >= 0 and summary["cost_usd"] > 0
    log = await events(store, session_id)
    start_event = log[0]
    assert start_event["event"] == "session start"
    assert start_event["disclosure"] == DISCLOSURE and start_event["commit"] == "test"
    assert start_event["config"]["text"].startswith("# Carl's config file")
    assert start_event["mic"]["autoGainControl"] is True
    utterances = [e for e in log if e["event"] == "utterance"]
    assert [u["text"] for u in utterances] == ["Einstein reputtasi matematiikassa."]
    assert utterances[0]["id"] == "U1" and utterances[0]["speaker"] == "1"
    assert any(e["event"] == "stt" and e["raw"] == {"said": "Einstein reputtasi matematiikassa."} for e in log)
    assert log[-1]["event"] == "session end"
    audio = await store.list(f"recordings/{session_id}/audio/")
    assert b"".join([await store.get(k) for k in audio]) == b"\1\0" * 16000
    assert stream.closed


async def test_a_normal_session_records_nothing(unlocked, stt, store):
    ws = await connect(unlocked)
    state = await start(ws, record=False)
    assert not state["recording"]
    await ws.send_bytes(b"\0" * 3200)
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    assert ended["summary"]["recording"] == "none"
    assert await store.list("recordings/") == []


async def test_pause_closes_the_stream_and_resume_opens_a_fresh_one(unlocked, stt, store):
    ws = await connect(unlocked)
    await start(ws)
    await ws.send_json({"type": "pause"})
    paused = await receive(ws, "session")
    assert paused["state"] == "paused" and not paused["recording"]
    assert stt.streams[0].finalized == 1 and stt.streams[0].closed
    assert stt.streams[0].audio.endswith(b"\0" * 6400)  # silence before the finalise
    await ws.send_bytes(b"\0" * 3200)  # nothing is heard or kept while paused
    await ws.send_json({"type": "resume"})
    resumed = await receive(ws, "session")
    assert resumed["state"] == "listening" and resumed["recording"]
    assert len(stt.streams) == 2 and stt.streams[1].audio == b""
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")


async def test_a_page_rejoins_its_session_after_a_drop(unlocked, stt):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.close()
    await settle()
    assert stt.streams[0].finalized == 1 and not stt.streams[0].closed  # the drop finalises
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    state = await receive(ws, "session")
    assert state["session"] == session_id and state["state"] == "listening"
    await ws.send_bytes(b"\2\0" * 1600)
    await settle()
    assert stt.streams[0].audio.endswith(b"\2\0" * 1600) and len(stt.streams) == 1
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")


@pytest.fixture
def app_config(config):
    return quick(config, grace_s=0.3)


async def test_the_session_ends_after_the_grace_period(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.close()
    await asyncio.sleep(0.6)
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    ended = await receive(ws, "ended")
    assert ended["summary"]["recording"] == "kept"
    assert stt.streams[0].closed
    assert (await events(store, session_id))[-1]["reason"] == "page gone"


async def test_stop_recording_deletes_everything_at_once(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.send_bytes(b"\1\0" * 1600)
    stt.streams[0].say("1", "Tämä jää talteen.")
    await settle()
    await ws.send_json({"type": "stop_recording", "session": session_id})
    assert (await receive(ws, "recording_stopped"))["session"] == session_id
    state = await receive(ws, "session")
    assert state["state"] == "listening" and not state["recording"]
    await ws.send_bytes(b"\1\0" * 1600)
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    assert ended["summary"]["recording"] == "stopped"
    assert await store.list(f"recordings/{session_id}/") == []


async def test_a_stop_after_the_end_still_deletes(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert await store.list(f"recordings/{session_id}/")
    await ws.send_json({"type": "stop_recording", "session": session_id})
    await receive(ws, "recording_stopped")
    assert await store.list(f"recordings/{session_id}/") == []
    await ws.send_json({"type": "stop_recording", "session": "../../costs"})
    await ws.send_json({"type": "heartbeat"})
    deadline = asyncio.get_running_loop().time() + 0.2
    while (left := deadline - asyncio.get_running_loop().time()) > 0:
        with contextlib.suppress(asyncio.TimeoutError):
            assert (await ws.receive_json(timeout=left))["type"] != "recording_stopped"


async def test_the_month_cost_reaches_the_start_screen(unlocked, stt):
    ws = await connect(unlocked)
    await start(ws)
    await asyncio.sleep(0.1)
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")
    ws = await unlocked.ws_connect("/api/ws")
    hello = await ws.receive_json(timeout=1)
    assert hello["costs"]["month_usd"] > 0
    assert ended["summary"]["month_eur"] is not None


async def test_nothing_is_recorded_without_a_confirmed_disclosure(unlocked, stt, store):
    ws = await connect(unlocked)
    for disclosure in [None, {"text": "", "confirmed_at": "2026-09-27T18:02:11Z"}, {"text": "Tämä on testi."}]:
        await ws.send_json({"type": "start", "record": True, "disclosure": disclosure, "mic": {}, "timezone": "UTC"})
        state = await receive(ws, "session")
        assert not state["recording"]
        await ws.send_json({"type": "end"})
        assert (await receive(ws, "ended"))["summary"]["recording"] == "none"
    assert await store.list("recordings/") == []


async def test_a_page_that_leaves_right_after_end(unlocked, stt):
    ws = await connect(unlocked)
    await start(ws, record=False)
    await ws.send_json({"type": "end"})
    await ws.close()
    await settle()
    assert stt.streams[0].closed


async def test_a_start_resent_after_a_drop_carries_on_the_same_session(unlocked, stt, store):
    ws = await connect(unlocked)
    start_message = {"type": "start", "record": True, "disclosure": DISCLOSURE, "mic": {}, "timezone": "UTC",
                     "start_id": "7c1e0a52-3f4d-4b8e-9a51-0d2f6c8e4b17"}
    await ws.send_json(start_message)
    first = await receive(ws, "session")
    await ws.close()
    await settle()
    ws = await connect(unlocked)
    await ws.send_json(start_message)
    again = await receive(ws, "session")
    assert again["session"] == first["session"] and len(stt.streams) == 1
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert len({k.split("/")[1] for k in await store.list("recordings/")}) == 1


async def test_end_waits_for_a_decision_still_running(unlocked, stt, store):
    from carl.server import SESSIONS

    class SlowDecider:
        async def on_utterance(self, session, heard):
            await asyncio.sleep(0.3)
            session.log("decision", utterance=heard.id, outcome="none")

    unlocked.server.app[SESSIONS].decider = SlowDecider()
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    stt.streams[0].say("1", "Pariisi on Italian pääkaupunki.")
    await settle()
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    names = [e["event"] for e in await events(store, session_id)]
    assert names.index("decision") < names.index("session end")
