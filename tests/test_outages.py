"""Step 7: can't hear, can't check, the failure log and Soniox rotation."""

import asyncio
import contextlib
import dataclasses
import json
import time

import pytest

from carl import session as session_module
from carl.checks import Checker
from carl.decision import Decider
from carl.outages import FailureLog, now_iso
from carl.server import SESSIONS
from carl.session import Session, Sessions
from carl.settle import Settler
from carl.storage import MemoryStore
from carl.stt import SttError

from .conftest import ScriptedStt, quick
from .test_checks import (
    FI_CARD, SUPPORTED, FakeFinder, FakeLink, FakeTyped, check, olympics, prompts, reply, say, until,  # noqa: F401
)
from .test_decision import Events
from .test_decision import FakeModel as DecisionModel
from .test_session import connect, events, receive, start
from .test_settle import SettleModel


@pytest.fixture
def sessions(config, prompts, store, stt):  # noqa: F811 - `prompts` is the imported fixture
    return Sessions(config, prompts, store, stt, "test")


@pytest.fixture
def session(sessions):
    session = Session(sessions, "20260927T180000Z-abcdef", record=True, timezone="Europe/Helsinki")
    session.recorder = Events()
    session.link = FakeLink()
    return session


async def written(sessions):
    """The failure log's records, once written."""
    await sessions.failures.flush()
    return await sessions.failures.records(now_iso()[:10])


def indicators(session):
    return [(m["problem"], m["reason"]) for m in session.link.sent if m["type"] == "indicator"]


async def settle_down(session):
    for _ in range(5):
        await asyncio.sleep(0)
    while session.checks:
        await asyncio.wait(set(session.checks))
    await asyncio.sleep(0)


# --- The failure log -----------------------------------------------------------------------------


async def test_the_failure_log_is_a_jsonl_file_a_day(store):
    failures = FailureLog(store)
    failures.add({"type": "entry", "time": "2026-09-27T18:00:00.000Z", "stage": "decision", "kind": "timeout"})
    failures.add({"type": "entry", "time": "2026-09-27T18:00:01.000Z", "stage": "settle", "kind": "timeout"})
    failures.add({"type": "entry", "time": "2026-09-28T00:00:01.000Z", "stage": "mic", "kind": "mic-lost"})
    await failures.flush()
    assert await store.list("failures/") == ["failures/2026-09-27.jsonl", "failures/2026-09-28.jsonl"]
    assert [r["stage"] for r in await failures.records("2026-09-27")] == ["decision", "settle"]
    again = FailureLog(store)  # after a restart it appends to what is there
    again.add({"type": "entry", "time": "2026-09-28T00:05:00.000Z", "stage": "connection", "kind": "dropped"})
    await again.flush()
    assert [r["stage"] for r in await again.records("2026-09-28")] == ["mic", "connection"]


async def test_a_failed_write_keeps_its_records_queued():
    class Flaky(MemoryStore):
        fail = True

        async def put(self, key, data):
            if self.fail:
                raise OSError("the bucket is down")
            await super().put(key, data)

    store = Flaky()
    failures = FailureLog(store)
    failures.add({"type": "entry", "time": "2026-09-27T18:00:00.000Z", "kind": "timeout"})
    await failures.flush()
    assert await store.list("failures/") == [] and failures.pending
    store.fail = False
    failures.add({"type": "entry", "time": "2026-09-27T18:00:05.000Z", "kind": "unavailable"})
    await failures.flush()
    assert [r["kind"] for r in await failures.records("2026-09-27")] == ["timeout", "unavailable"]


async def test_an_entry_holds_no_provider_text_but_the_recording_does(sessions, session):
    await check(sessions, session, olympics(session), FakeFinder("unavailable"))
    [entry] = [r for r in await written(sessions) if r["type"] == "entry"]
    assert entry | {"time": 0} == {"type": "entry", "time": 0, "session": session.id, "stage": "fact-finding B",
                                   "kind": "unavailable", "provider": "perplexity",
                                   "model": "google/gemini-3.8-flash", "status": 503, "code": None,
                                   "candidate": "C1"}
    assert "1956" not in json.dumps(await written(sessions))
    assert session.recorder.of("failure")[0]["error_text"] == "the provider's full text"


# --- Can't check: the decision model ---------------------------------------------------------------


async def decide(sessions, session, *replies):
    decider = Decider(sessions, DecisionModel(*replies))
    for i, _ in enumerate(replies):
        await decider.on_utterance(session, say(session, f"Lause numero {i} tässä.", ago=0.5))
    await settle_down(session)


async def test_three_failed_decision_calls_in_a_row_mean_cant_check(sessions, session):
    assert sessions.config.outages.decision_failures == 3
    await decide(sessions, session, "timeout", "unavailable")
    assert session.health.indicator() == (None, None) and indicators(session) == []
    await decide(sessions, session, "bad output")
    assert session.health.indicator() == ("cant_check", "decision")
    assert indicators(session) == [("cant_check", "decision")]
    await decide(sessions, session, "timeout", ("none", {"none": 1.0}))
    assert session.health.indicator() == (None, None)
    assert indicators(session) == [("cant_check", "decision"), (None, None)]
    outages = [r for r in await written(sessions) if r["type"] == "outage"]
    assert [(o["reason"], o["end"] is None, o.get("utterances_skipped")) for o in outages] == [
        ("decision", True, 3), ("decision", False, 4)]  # every utterance dropped since the model last worked
    assert outages[0]["id"] == outages[1]["id"] and outages[0]["problem"] == "cant_check"
    assert [e["utterances_skipped"] for e in session.recorder.of("outage")] == [3, 4]


async def test_a_success_between_failures_starts_the_count_again(sessions, session):
    await decide(sessions, session, "timeout", "timeout", ("none", {"none": 1.0}), "timeout", "timeout")
    assert session.health.indicator() == (None, None)


async def test_settle_calls_count_with_the_decision_calls(sessions, session):
    await decide(sessions, session, "timeout", "timeout")
    candidate = olympics(session)
    candidate.state = "finding"
    heard = say(session, "Ei kun 1952.", ago=0.2)
    await Settler(sessions, SettleModel("timeout")).on_utterance(session, heard)
    assert session.health.indicator() == ("cant_check", "decision")
    await Settler(sessions, SettleModel()).on_utterance(session, say(session, "Tai sitten ei.", ago=0.1))
    assert session.health.indicator() == (None, None)


# --- Can't check: fact-finding and fact-checking --------------------------------------------------------


async def test_two_candidates_whose_fact_finders_all_fail_mean_cant_check(sessions, session):
    assert sessions.config.outages.check_failures == 2
    await check(sessions, session, olympics(session), FakeFinder("timeout"))
    assert session.health.indicator() == (None, None)
    await check(sessions, session, olympics(session), FakeFinder("unavailable"))
    assert session.health.indicator() == ("cant_check", "fact-finding")
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is right")))
    assert session.health.indicator() == (None, None)


async def test_one_fact_finder_down_is_not_cant_check(sessions, session):
    for _ in range(3):
        finders = {"A": FakeFinder("unavailable", letter="A"), "B": FakeFinder(reply("claim is right"))}
        await check(sessions, session, olympics(session), finders)
    assert session.health.indicator() == (None, None)
    assert [r["stage"] for r in await written(sessions) if r["type"] == "entry"] == ["fact-finding A"] * 3


async def test_two_candidates_left_without_a_verdict_mean_cant_check(sessions, session):
    for _ in range(2):
        await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", FI_CARD)),
                    FakeTyped("timeout"))
    assert session.health.indicator() == ("cant_check", "fact-checking")
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", FI_CARD)),
                FakeTyped(SUPPORTED))
    assert session.health.indicator() == (None, None)


async def test_a_candidate_with_no_fact_checking_call_leaves_the_count_alone(sessions, session):
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", FI_CARD)),
                FakeTyped("timeout"))
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is right")))  # no call made
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is wrong", FI_CARD)),
                FakeTyped("timeout"))
    assert session.health.indicator() == ("cant_check", "fact-checking")


async def test_overload_never_changes_the_indicator(sessions, session):
    for _ in range(8):
        olympics(session).state = "finding"
    checker = Checker(sessions, {"B": FakeFinder()}, FakeTyped())
    for _ in range(3):
        assert checker.start(session, olympics(session)) is None
    assert session.health.indicator() == (None, None)
    assert [r["kind"] for r in await written(sessions) if r["type"] == "entry"] == ["overload"] * 3


async def test_the_timeout_counts_against_the_stage_it_was_stuck_in(sessions, session):
    sessions.config = dataclasses.replace(
        sessions.config, candidates=dataclasses.replace(sessions.config.candidates, timeout_s=2.2))

    async def slow(request):
        await asyncio.sleep(0.4)
        return reply("claim is right")

    await asyncio.gather(*(check(sessions, session, olympics(session), FakeFinder(slow)) for _ in range(2)))
    assert session.health.indicator() == ("cant_check", "fact-finding")


# --- Can't hear, and which one wins ------------------------------------------------------------------------


def test_cant_hear_wins_over_cant_check(sessions, session):
    health = session.health
    for reason in ("fact-checking", "decision", "stt-reopening", "mic-lost"):
        health.begin(reason)
    assert health.indicator() == ("cant_hear", "mic-lost")
    health.end("mic-lost")
    assert health.indicator() == ("cant_hear", "stt-reopening")
    health.end("stt-reopening")
    assert health.indicator() == ("cant_check", "decision")


def test_the_recording_mark_goes_off_while_no_audio_can_arrive(sessions, session):
    class Recording:
        active, failing = True, False

        def log(self, event, **fields):
            pass

    session.recorder = Recording()
    assert session.recording
    session.health.begin("stt-reopening")  # audio still reaches the recording
    assert session.recording
    session.health.begin("mic-lost")
    assert not session.recording
    session.health.end("mic-lost")
    session.recorder.failing = True  # nothing reaches storage
    assert not session.recording


async def test_a_recording_that_cant_write_turns_the_mark_off(sessions):
    class Down(MemoryStore):
        async def put(self, key, data):
            if key.startswith("recordings/"):
                raise OSError("the bucket is down")
            await super().put(key, data)

    sessions.store = Down()
    session = Session(sessions, "20260927T180000Z-abcdef", record=True, timezone="Europe/Helsinki")
    session.link = FakeLink()
    await session.begin({})
    assert session.recording
    session.log("something", n=1)
    await session.recorder.flush()
    await asyncio.sleep(0)
    assert not session.recording
    assert session.link.sent[-1] == session.state_message() and session.link.sent[-1]["recording"] is False
    await session.end("end")


# --- Through the WebSocket ------------------------------------------------------------------------------------


@pytest.fixture
def app_config(config):
    config = quick(config, silence_s=5)
    return dataclasses.replace(config, outages=dataclasses.replace(config.outages, no_audio_s=0.3))


async def indicator(ws, timeout=2):
    message = await receive(ws, "indicator", timeout)
    return message["problem"], message["reason"]


@contextlib.asynccontextmanager
async def talking(ws):
    """Audio every 100 ms while inside."""

    async def talk():
        while True:
            await ws.send_bytes(b"\1\0" * 1600)
            await asyncio.sleep(0.1)

    task = asyncio.create_task(talk())
    try:
        yield
    finally:
        task.cancel()


async def test_the_indicator_comes_after_start(unlocked, stt):
    ws = await connect(unlocked)
    await start(ws)
    assert await indicator(ws) == (None, None)
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")


async def test_no_audio_while_listening_means_cant_hear_until_it_comes(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    assert await indicator(ws) == (None, None)
    assert await indicator(ws) == ("cant_hear", "no-audio")
    state = await receive(ws, "session")
    assert state["recording"] is False  # nothing reaches the recording either
    await ws.send_bytes(b"\1\0" * 1600)
    assert await indicator(ws) == (None, None)
    assert (await receive(ws, "session"))["recording"] is True
    await ws.send_json({"type": "pause"})
    await receive(ws, "session")
    await asyncio.sleep(0.5)  # not while paused
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    failures = await unlocked.server.app[SESSIONS].failures.records(now_iso()[:10])
    assert [(r["type"], r.get("stage"), r.get("kind")) for r in failures] == [
        ("entry", "mic", "no-audio"), ("outage", "mic", None), ("outage", "mic", None)]
    assert all(r["session"] == session_id for r in failures)
    assert [e["reason"] for e in await events(store, session_id) if e["event"] == "outage"] == ["no-audio"] * 2


async def test_a_dropped_connection_is_cant_hear_until_audio_flows_again(unlocked, stt):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.close()
    for _ in range(20):
        await asyncio.sleep(0.01)
    session = unlocked.server.app[SESSIONS].get(session_id)
    assert session.health.indicator() == ("cant_hear", "connection")
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    state = await receive(ws, "session")
    assert state["recording"] is False
    assert await indicator(ws) == ("cant_hear", "connection")
    async with talking(ws):
        assert await indicator(ws) == (None, None)
        assert (await receive(ws, "session"))["recording"] is True
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    records = await unlocked.server.app[SESSIONS].failures.records(now_iso()[:10])
    entries = [r for r in records if r["type"] == "entry"]
    assert [(e["stage"], e["kind"]) for e in entries] == [("connection", "dropped")]
    outages = [r for r in records if r["type"] == "outage"]
    assert [(o["reason"], o["end"] is not None) for o in outages] == [("connection", False), ("connection", True)]


async def test_the_handover_is_no_drop(unlocked, stt):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    assert await indicator(ws) == (None, None)
    async with talking(ws):
        second = await connect(unlocked)
        await second.send_json({"type": "rejoin", "session": session_id})
        await receive(second, "session")
        assert await indicator(second) == (None, None)
    async with talking(second):
        await ws.close()
        await asyncio.sleep(0.4)
        session = unlocked.server.app[SESSIONS].get(session_id)
        assert session.health.indicator() == (None, None) and session.health.open == {}
    await second.send_json({"type": "end"})
    await receive(second, "ended")
    records = await unlocked.server.app[SESSIONS].failures.records(now_iso()[:10])
    assert records == []


async def test_a_lost_microphone_is_cant_hear_until_it_is_back(unlocked, stt):
    ws = await connect(unlocked)
    await start(ws)
    async with talking(ws):
        assert await indicator(ws) == (None, None)
        await ws.send_json({"type": "mic", "state": "lost", "detail": "muted"})
        assert await indicator(ws) == ("cant_hear", "mic-lost")
        assert (await receive(ws, "session"))["recording"] is False
        await ws.send_json({"type": "mic", "state": "back"})
        assert await indicator(ws) == (None, None)
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    records = await unlocked.server.app[SESSIONS].failures.records(now_iso()[:10])
    assert [(r["type"], r["stage"], r.get("kind"), r.get("detail")) for r in records] == [
        ("entry", "mic", "mic-lost", None), ("outage", "mic", None, "muted"), ("outage", "mic", None, "muted")]


async def test_the_pages_buffered_events_go_to_the_logs(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    events_sent = [
        {"kind": "gap", "start": "2026-09-27T18:04:00.000Z", "end": "2026-09-27T18:04:09.000Z"},
        {"kind": "mic-lost", "start": "2026-09-27T18:05:00.000Z", "end": "2026-09-27T18:05:30.000Z",
         "detail": "ended"},
        {"kind": "hidden", "start": "2026-09-27T18:05:00.000Z", "end": "2026-09-27T18:05:30.000Z"},
        {"kind": "wake-lock", "at": "2026-09-27T18:05:00.000Z", "state": "refused"},
        {"kind": "card-render-failed", "at": "2026-09-27T18:06:00.000Z", "id": "C3", "stack": "x" * 5000},
        "not an event",
    ]
    async with talking(ws):
        await ws.send_json({"type": "page_events", "events": events_sent})
        await asyncio.sleep(0.1)
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    records = await unlocked.server.app[SESSIONS].failures.records(now_iso()[:10])
    assert [(r["reason"], r["stage"], r["start"], r["end"], r["source"]) for r in records] == [
        ("connection", "connection", "2026-09-27T18:04:00.000Z", "2026-09-27T18:04:09.000Z", "page"),
        ("mic-lost", "mic", "2026-09-27T18:05:00.000Z", "2026-09-27T18:05:30.000Z", "page")]
    logged = [e for e in await events(store, session_id) if e["event"] == "page event"]
    assert [e["kind"] for e in logged] == ["gap", "mic-lost", "hidden", "wake-lock", "card-render-failed"]
    assert "stack" not in logged[-1] and logged[-1]["id"] == "C3"


# --- Speech-to-text: reopening and rotation ----------------------------------------------------------------------


class FlakyStt(ScriptedStt):
    """Speech-to-text whose first `fails` opens fail."""

    def __init__(self, fails):
        super().__init__()
        self.fails, self.opens = fails, []

    async def open(self, languages):
        self.opens.append(time.monotonic())
        if len(self.opens) <= self.fails:
            raise SttError("unavailable", "HTTP 503")
        return await super().open(languages)


async def test_a_dropped_stream_reopens_at_once_then_backs_off(sessions, session, monkeypatch):
    monkeypatch.setattr(session_module, "REOPEN_BACKOFF_S", (0, 0.05, 0.1, 0.2))
    sessions.stt = stt = FlakyStt(fails=3)
    session.recorder = None
    await session.begin({})
    assert session.health.indicator() == ("cant_hear", "stt-reopening")
    await until(lambda: session.run is not None)
    gaps = [b - a for a, b in zip(stt.opens, stt.opens[1:])]
    assert len(stt.opens) == 4 and gaps[0] < gaps[1] < gaps[2]  # at once, then longer and longer
    assert session.health.indicator() == (None, None)
    assert [(r["type"], r.get("stage"), r.get("kind")) for r in await written(sessions)] == [
        ("entry", "speech-to-text", "unavailable"), ("outage", "speech-to-text", None),
        ("entry", "speech-to-text", "unavailable"), ("entry", "speech-to-text", "unavailable"),
        ("outage", "speech-to-text", None)]
    await session.end("end")


async def test_a_stream_that_drops_is_reopened_with_a_gap(sessions, session, stt):
    session.recorder = None
    await session.begin({})
    first = session.run
    session.stream_failed(first, SttError("unavailable", "closed"))
    assert session.health.indicator() == ("cant_hear", "stt-reopening")
    await until(lambda: session.run is not None)
    assert session.run is not first and len(stt.streams) == 2
    assert session.heard[-1].kind == "gap" and session.health.indicator() == (None, None)
    await session.end("end")


async def test_a_stream_nearing_its_limit_is_replaced_at_a_segment_end(sessions, session, stt, monkeypatch):
    monkeypatch.setattr(session_module, "ROTATE_AFTER_S", 0.2)
    session.recorder = None
    await session.begin({})
    first = stt.streams[0]
    first.say("1", "Tämä sanotaan ensimmäiseen virtaan.", endpoint=True)
    await until(lambda: session.utterance_count == 1)
    assert len(stt.streams) == 1  # too young to rotate
    await asyncio.sleep(0.25)
    first.say("1", "Ja tämä vielä samaan virtaan.", endpoint=True)
    await until(lambda: len(stt.streams) == 2 and first.closed)
    await until(lambda: session.heard[-1].__class__.__name__ == "Marker")
    second = stt.streams[1]
    second.say("1", "Tämä kuuluu uuteen virtaan.", endpoint=True)
    await until(lambda: session.utterance_count == 3)
    assert [getattr(h, "id", "(gap)") for h in session.heard] == ["U1", "U2", "(gap)", "U3"]
    assert [h.stream for h in session.heard if hasattr(h, "stream")] == [1, 1, 2]
    assert session.health.indicator() == (None, None)  # a rotation is no failure
    await session.end("end")
