"""Step 7: saving each session's state, and resuming it after a restart."""

import asyncio
import json
import time

import pytest

from carl import resume
from carl.decision import Candidate
from carl.gate import COOKIE
from carl.language import CardLanguage
from carl.location import Place
from carl.outages import now_iso
from carl.prompts import load_prompts
from carl.resume import SessionStates, restore
from carl.server import SESSIONS, close_sockets, create_app
from carl.session import Card, Heard, Marker, Session, Sessions
from carl.stt.fake import words
from carl.utterances import Utterance

from .conftest import PASSWORD, ROOT, ScriptedStt, quick
from .test_session import connect, events, receive, start

SESSION = "20260927T180000Z-abcdef"


def heard(n, text, ago, stream=1, speaker="1"):
    return Heard(f"U{n}", stream, Utterance(speaker, words(speaker, text)), time.time() - ago)


def fi() -> CardLanguage:
    return CardLanguage("fi", "too few words", {"fi": 4}, {"fi": 4})


def saved_session(sessions, record=True) -> Session:
    """A session as it might be when the server stops: an old utterance out of
    the context window, recent ones with a marker, candidates in every kind
    of state, and cards sent, shown and filed."""
    session = Session(sessions, SESSION, record=record, timezone="Europe/Helsinki", start_id="start-1")
    session.started = time.time() - 600
    session.listening_s, session.listening_since = 400.0, time.time() - 100
    session.cost_usd, session.streams, session.utterance_count = 0.0123, 2, 6
    session.place = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    old = heard(1, "Tämä sanottiin kauan sitten.", ago=300)
    recent = [heard(2, "Helsingissä on ollut olympialaisetkin.", ago=60),
              heard(3, "Joo, vuonna 1956.", ago=58, speaker="2"),
              heard(4, "Kuka näytteli Rickiä?", ago=40),
              heard(5, "Eiffel-torni on 200 metriä.", ago=30, stream=2),
              heard(6, "Suomessa on kaksi miljoonaa järveä.", ago=20, stream=2)]
    session.heard = [old, *recent[:3], Marker("gap", time.time() - 35), *recent[3:]]
    states = ["card history", "on screen", "ready", "finding", "checking", "silent"]
    for i, (h, state) in enumerate(zip([old, *recent], states, strict=True), 1):
        c = Candidate(f"C{i}", "open question" if i == 3 else "claim", h, 0.9, fi(), state=state)
        c.restatement = f"Väite {i}." if i != 4 else None
        session.candidates.append(c)
        if state in ("card history", "on screen", "ready"):
            session.cards[c.id] = Card(c.id, {"id": c.id, "kind": "claim", "fact": f"Fakta {i}."}, h.time, c, state,
                                       h.time + 8, "2026-09-27T18:00:00.000Z" if state != "ready" else None,
                                       h.time + 9 if state != "ready" else None)
    session.disputing = {"U9": "C2"}
    return session


@pytest.fixture
def sessions(config, store, stt):
    sessions = Sessions(quick(config), {}, store, stt, "test")
    resume.install(sessions)
    return sessions


# --- Saving ---------------------------------------------------------------------------------------------


async def test_the_state_round_trips_without_coordinates(sessions, store):
    session = saved_session(sessions)
    await sessions.states.save(session)
    [key] = await store.list("sessions/")
    assert key == f"sessions/{SESSION}/state.json"
    saved = json.loads(await store.get(key))
    state = saved["state"]
    assert not {"lat", "lon", "accuracy_m"} & set(json.dumps(state).replace('"', " ").split())
    assert state["place"] == {"neighbourhood": "Kallio", "city": "Helsinki", "region": "Uusimaa",
                              "country": "Suomi / Finland", "country_code": "FI"}
    assert [h.get("id", h.get("marker")) for h in state["heard"]] == ["U2", "U3", "U4", "gap", "U5", "U6"]
    again = restore(sessions, state, saved["saved"])
    assert again.id == SESSION and again.start_id == "start-1" and again.record and again.timezone == "Europe/Helsinki"
    assert again.cost_usd == pytest.approx(0.0123) and again.streams == 2 and again.utterance_count == 6
    assert 499 <= again.listening_s <= 501  # up to when it was saved
    assert again.place == session.place and again.disputing == {"U9": "C2"}
    assert [(c.id, c.kind, c.state, c.restatement) for c in again.candidates] == [
        (c.id, c.kind, c.state, c.restatement) for c in session.candidates]
    assert again.candidates[3].shown_as == "Kuka näytteli Rickiä?"  # the raw utterance, with no restatement
    assert again.candidates[1].heard is again.heard[0]  # the same utterance as in the context
    assert again.candidates[0].heard.utterance.text == "Tämä sanottiin kauan sitten."
    assert {c.id: c.state for c in again.cards.values()} == {"C1": "card history", "C2": "on screen", "C3": "ready"}
    assert again.cards["C2"].candidate is again.candidates[1]
    assert [c["id"] for c in again.cards_message()["waiting"]] == ["C3"]


async def test_the_state_is_saved_as_it_changes(sessions, store, monkeypatch):
    puts = []
    real = store.put

    async def put(key, data):
        puts.append(key)
        await real(key, data)

    monkeypatch.setattr(store, "put", put)
    session = saved_session(sessions, record=False)
    session.start_saving()
    await asyncio.sleep(0.05)
    assert puts == []  # nothing urgent: at most every few seconds
    session.save_soon()
    await asyncio.sleep(0.05)
    assert puts == [f"sessions/{SESSION}/state.json"]
    session.save_soon()  # nothing changed
    await asyncio.sleep(0.05)
    assert len(puts) == 1
    session.card_reported("filed", "C2", "2026-09-27T18:06:00.000Z")
    await asyncio.sleep(0.05)
    assert len(puts) == 2
    saved = json.loads(await store.get(f"sessions/{SESSION}/state.json"))
    assert {c["id"]: c["state"] for c in saved["state"]["cards"]}["C2"] == "card history"
    await session.stop_saving()


# --- Resuming -------------------------------------------------------------------------------------------------


async def unlock(client):
    response = await client.post("/api/unlock", data={"pass": PASSWORD}, allow_redirects=False)
    client.session.cookie_jar.update_cookies({COOKIE: response.cookies[COOKIE].value})
    return client


async def instance(aiohttp_client, config, passes, store, stt, grace_s=120):
    """A server instance on `store`, saving and resuming sessions."""
    config = quick(config, grace_s=grace_s)
    sessions = Sessions(config, {}, store, stt, "test")
    resume.install(sessions)
    return await unlock(await aiohttp_client(create_app(config, {}, passes, sessions)))


async def saved_before(config, store):
    """What the last instance left: a saved session, and its recording so far."""
    earlier = Sessions(quick(config), {}, store, ScriptedStt(), "test")
    resume.install(earlier)
    await earlier.states.save(saved_session(earlier))
    for key in ("events/000001.jsonl", "events/000002.jsonl", "audio/000001.pcm"):
        await store.put(f"recordings/{SESSION}/{key}", b'{"time": "x", "event": "old"}\n')


async def test_a_saved_session_waits_for_its_page_and_carries_on(aiohttp_client, config, passes, store):
    await saved_before(config, store)
    stt = ScriptedStt()
    client = await instance(aiohttp_client, config, passes, store, stt)
    sessions = client.server.app[SESSIONS]
    session = sessions.get(SESSION)
    assert session is not None and session.grace is not None
    assert stt.streams == []  # no stream is paid for until the page is back
    assert session.health.indicator() == ("cant_hear", "connection")
    assert [c.state for c in session.candidates] == ["card history", "on screen", "ready", "failed", "failed",
                                                     "silent"]
    assert isinstance(session.heard[-1], Marker) and session.heard[-1].kind == "gap"
    ws = await connect(client)
    await ws.send_json({"type": "rejoin", "session": SESSION})
    state = await receive(ws, "session")
    assert state["state"] == "listening" and state["recording"] is False  # until audio arrives
    assert (await receive(ws, "indicator"))["problem"] == "cant_hear"
    cards = await receive(ws, "cards")
    assert cards["current"]["id"] == "C2" and [c["id"] for c in cards["waiting"]] == ["C3"]
    assert [c["id"] for c in cards["history"]] == ["C1"]
    for _ in range(20):
        if stt.streams:
            break
        await asyncio.sleep(0.01)
    assert len(stt.streams) == 1 and session.run.index == 3  # fresh labels, C for the third stream
    await ws.send_bytes(b"\1\0" * 1600)
    assert (await receive(ws, "indicator"))["problem"] is None
    assert (await receive(ws, "session"))["recording"] is True
    stt.streams[0].say("1", "Nyt jatketaan.")
    await asyncio.sleep(0.05)
    assert session.heard[-1].id == "U7"
    await ws.send_json({"type": "end"})
    summary = (await receive(ws, "ended"))["summary"]
    assert summary["listening_s"] >= 500 and summary["cost_usd"] >= 0.0123
    assert await store.list("sessions/") == []  # deleted at End
    log = await events(store, SESSION)
    keys = await store.list(f"recordings/{SESSION}/events/")
    assert keys[:2] == [f"recordings/{SESSION}/events/000001.jsonl", f"recordings/{SESSION}/events/000002.jsonl"]
    assert await store.get(keys[0]) == b'{"time": "x", "event": "old"}\n'  # nothing overwritten
    names = [e["event"] for e in log]
    assert names.index("session resumed") < names.index("session end")
    lost = [e for e in log if e["event"] == "failure" and e["kind"] == "lost-in-restart"]
    assert [(e["stage"], e["candidate"]) for e in lost] == [("fact-finding", "C4"), ("fact-checking", "C5")]
    records = await sessions.failures.records(now_iso()[:10])
    assert [(r["stage"], r["kind"]) for r in records if r["type"] == "entry"] == [
        ("fact-finding", "lost-in-restart"), ("fact-checking", "lost-in-restart"), ("connection", "dropped")]


async def test_a_saved_session_whose_page_doesnt_come_back_ends(aiohttp_client, config, passes, store):
    await saved_before(config, store)
    stt = ScriptedStt()
    client = await instance(aiohttp_client, config, passes, store, stt, grace_s=0.3)
    sessions = client.server.app[SESSIONS]
    await asyncio.sleep(0.6)
    assert sessions.get(SESSION) is None and sessions.ended[SESSION].recording == "kept"
    assert stt.streams == [] and await store.list("sessions/") == []
    log = await events(store, SESSION)
    assert log[-1]["event"] == "session end" and log[-1]["reason"] == "page gone"


async def test_an_unreadable_state_is_left_alone(aiohttp_client, config, passes, store, caplog):
    await store.put("sessions/20260927T170000Z-000000/state.json", b"not json")
    client = await instance(aiohttp_client, config, passes, store, ScriptedStt())
    assert client.server.app[SESSIONS].live == {} and "couldn't resume" in caplog.text


async def test_a_resent_start_finds_its_resumed_session(aiohttp_client, config, passes, store):
    await saved_before(config, store)
    client = await instance(aiohttp_client, config, passes, store, ScriptedStt())
    ws = await connect(client)
    await ws.send_json({"type": "start", "record": True, "mic": {}, "timezone": "UTC", "start_id": "start-1"})
    assert (await receive(ws, "session"))["session"] == SESSION


# --- Shutting down ------------------------------------------------------------------------------------------------


async def test_a_shutdown_saves_each_session_instead_of_ending_it(aiohttp_client, config, passes, store):
    stt = ScriptedStt()
    client = await instance(aiohttp_client, config, passes, store, stt)
    ws = await connect(client)
    session_id = (await start(ws))["session"]
    await ws.send_bytes(b"\1\0" * 1600)
    stt.streams[0].say("1", "Tämä sanotaan ennen uudelleenkäynnistystä.")
    await asyncio.sleep(0.05)
    sessions = client.server.app[SESSIONS]
    await close_sockets(client.server.app)
    while (message := await ws.receive(timeout=1)).type.name == "TEXT":
        pass
    assert message.type.name == "CLOSE" and ws.close_code == 1001
    session = sessions.get(session_id)
    assert session.suspended and session.summary is None and stt.streams[0].closed
    saved = json.loads(await store.get(f"sessions/{session_id}/state.json"))["state"]
    assert saved["state"] == "listening" and [h["id"] for h in saved["heard"]] == ["U1"]
    log = await events(store, session_id)
    names = [e["event"] for e in log]
    assert "session suspended" in names and "session end" not in names
    # The next instance picks it up.
    stt2 = ScriptedStt()
    client2 = await instance(aiohttp_client, config, passes, store, stt2)
    resumed = client2.server.app[SESSIONS].get(session_id)
    assert resumed is not None and resumed.heard[0].utterance.text == "Tämä sanotaan ennen uudelleenkäynnistystä."
    ws2 = await connect(client2)
    await ws2.send_json({"type": "rejoin", "session": session_id})
    assert (await receive(ws2, "session"))["session"] == session_id
    await ws2.send_json({"type": "end"})
    await receive(ws2, "ended")
    assert await store.list("sessions/") == []


async def test_without_saved_states_a_shutdown_ends_the_sessions(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await close_sockets(unlocked.server.app)
    assert unlocked.server.app[SESSIONS].ended[session_id].recording == "kept"
    assert await store.list("sessions/") == []


def test_saving_is_off_without_the_install(config, store, stt):
    sessions = Sessions(config, {}, store, stt, "test")
    assert sessions.states is None
    resume.install(sessions)
    assert isinstance(sessions.states, SessionStates)


async def test_a_lost_candidate_is_checked_anew_when_repeated(sessions):
    from carl.checks import Checker
    from carl.decision import Decider

    from .test_checks import FakeFinder, FakeTyped, reply, say
    from .test_decision import Events
    from .test_decision import FakeModel as DecisionModel

    sessions.prompts = load_prompts(ROOT / "prompts")
    session = saved_session(sessions, record=False)
    session.recorder = Events()
    sessions.states = None
    await session.carry_on()
    sessions.checker = Checker(sessions, {"B": FakeFinder(reply("claim is right"))}, FakeTyped())
    decider = Decider(sessions, DecisionModel(("same as C4", {"same as C4": 0.9})))
    await decider.on_utterance(session, say(session, "Se oli kyllä 1956.", ago=0.1))
    assert session.candidates[-1].repeat_of == "C4" and session.candidates[-1].state == "finding"
    for task in list(session.tasks):
        task.cancel()
