"""Step 8: each session's cost summary and the Start screen's last-session line."""

import asyncio
import json
import time

import pytest

from carl import resume
from carl.costs import Costs, SessionCosts, local_time, per_hour, session_key, stopped_line
from carl.decision import Decider
from carl.resume import restore, snapshot
from carl.server import SESSIONS
from carl.session import Session, Sessions

from .conftest import quick
from .test_checks import FakeFinder, FakeLink, check, olympics, prompts, reply, say  # noqa: F401
from .test_decision import Events
from .test_decision import FakeModel as DecisionModel
from .test_session import connect, receive, start


@pytest.fixture
def sessions(config, prompts, store, stt):  # noqa: F811 - `prompts` is the imported fixture
    return Sessions(config, prompts, store, stt, "test")


@pytest.fixture
def session(sessions):
    session = Session(sessions, "20260927T180000Z-abcdef", record=True, timezone="Europe/Helsinki")
    session.recorder = Events()
    session.link = FakeLink()
    return session


# --- The maths ------------------------------------------------------------------------------------------


def test_costs_add_up_per_stage_and_provider_actual_and_estimated():
    spend = SessionCosts()
    spend.add("speech-to-text", "soniox", 0.002)
    spend.add("decision", "openai", 0.00005)
    spend.add("decision", "openai", 0.00007, estimated=True)
    spend.add("fact-finding B", "perplexity", 0.0081, own_usd=0.00812)  # Perplexity's own figure counts
    spend.add("fact-finding A", "openai", 0.0117, own_usd=0.0117)
    spend.add("fact-checking", "openrouter", 0.00003, own_usd=0.000029)
    assert spend.usd == pytest.approx(0.002 + 0.00012 + 0.0081 + 0.0117 + 0.00003)
    assert spend.estimated_usd == pytest.approx(0.00007)
    event = spend.event()
    assert event["by_stage"]["decision"] == {"usd": 0.00012, "estimated_usd": 0.00007, "charges": 2}
    assert event["by_stage"]["fact-finding B"] == {"usd": 0.0081, "estimated_usd": 0.0, "charges": 1}
    assert event["by_provider"]["openai"] == {"usd": pytest.approx(0.01182), "estimated_usd": 0.00007,
                                              "charges": 3}
    assert event["provider_difference_usd"] == {"openrouter": 0.000001, "perplexity": -0.00002}
    assert SessionCosts.from_event(json.loads(json.dumps(event))).event() == event


def test_euros_per_listening_hour(config):
    rate = config.currency.ecb_usd_per_eur
    assert per_hour(config, 0.5, 59) is None  # too short to mean anything
    assert per_hour(config, 0.5, 3600) == pytest.approx(0.5 / rate, abs=1e-4)
    assert per_hour(config, 0.5, 1800) == pytest.approx(1.0 / rate, abs=1e-4)


def test_the_stopped_line_is_in_the_sessions_own_time():
    t = 1_790_000_000.0  # 2026-09-21 14:13:20 UTC
    assert local_time(t, "Europe/Helsinki") == "17:13" and local_time(t, "Nowhere/Else") == "14:13"
    assert stopped_line(t, "Europe/Helsinki") == "recording stopped and deleted at 17:13"


# --- A session's summary -----------------------------------------------------------------------------------


async def test_every_charge_reaches_the_sessions_summary_and_the_month(sessions, session):
    await Decider(sessions, DecisionModel(("none", {"none": 1.0}), "timeout")).on_utterance(
        session, say(session, "Otatko kahvia?"))
    await Decider(sessions, DecisionModel("timeout")).on_utterance(session, say(session, "Entä teetä?"))
    await check(sessions, session, olympics(session), FakeFinder(reply("claim is right")))
    await session.add_cost("speech-to-text", "soniox", "stt-rt-v5", 0.002)
    summary = session.cost_summary()
    assert summary["by_stage"]["decision"] == {"usd": pytest.approx(0.0000585 + 0.0000675),
                                               "estimated_usd": 0.0000675, "charges": 2}
    assert summary["by_stage"]["fact-finding B"]["usd"] == 0.0081
    assert summary["provider_difference_usd"] == {"perplexity": -0.00002}
    assert summary["usd"] == pytest.approx(session.cost_usd) == pytest.approx(session.spend.usd)
    assert summary["estimated_usd"] == 0.0000675
    month = await sessions.costs.month()
    assert month["usd"] == pytest.approx(session.cost_usd)
    assert month["by_stage"] == {k: pytest.approx(v["usd"]) for k, v in summary["by_stage"].items()}
    assert "Otatko" not in json.dumps(summary) and "1956" not in json.dumps(summary)  # no conversation


async def test_the_summary_is_written_at_the_start_and_for_good_at_end(unlocked, stt, store, config):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await asyncio.sleep(0.05)
    first = json.loads(await store.get(session_key(session_id)))
    assert first["ended"] is None and first["recording"] == "kept" and first["timezone"] == "Europe/Helsinki"
    stt.streams[0].say("1", "Tätä ei kirjoiteta yhteenvetoon.")
    await asyncio.sleep(0.05)
    await ws.send_json({"type": "end"})
    ended = (await receive(ws, "ended"))["summary"]
    summary = json.loads(await store.get(session_key(session_id)))
    assert summary["ended"] is not None and summary["duration_s"] >= summary["listening_s"] > 0
    assert summary["usd"] == pytest.approx(ended["cost_usd"], abs=1e-6)  # the page's summary keeps 6 decimals
    assert set(summary["by_stage"]) == {"speech-to-text"}
    assert summary["by_stage"]["speech-to-text"]["estimated_usd"] == 0
    assert "recording_stopped" not in summary and "kirjoiteta" not in json.dumps(summary)


async def test_a_stopped_recording_leaves_only_its_line(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    stt.streams[0].say("1", "Tämä poistetaan.")
    await ws.send_json({"type": "stop_recording", "session": session_id})
    await receive(ws, "recording_stopped")
    stopped_at = time.time()
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert await store.list(f"recordings/{session_id}/") == []
    summary = json.loads(await store.get(session_key(session_id)))
    assert summary["recording"] == "stopped"
    assert summary["recording_stopped"] in (stopped_line(stopped_at, "Europe/Helsinki"),
                                            stopped_line(stopped_at - 60, "Europe/Helsinki"))
    assert "poistetaan" not in json.dumps(summary)


async def test_a_stop_after_the_end_still_gets_its_line(unlocked, stt, store):
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    await ws.send_json({"type": "end"})
    await receive(ws, "ended")
    assert json.loads(await store.get(session_key(session_id)))["recording"] == "kept"
    await ws.send_json({"type": "stop_recording", "session": session_id})
    await receive(ws, "recording_stopped")
    summary = json.loads(await store.get(session_key(session_id)))
    assert summary["recording"] == "stopped"
    assert summary["recording_stopped"].startswith("recording stopped and deleted at ")


async def test_the_summary_is_kept_current_while_the_session_runs(sessions, session):
    resume.install(sessions)
    session.start_saving()
    await session.add_cost("decision", "openai", "gpt-6-luna", 0.00005)
    session.save_soon()
    await asyncio.sleep(0.05)
    summary = await sessions.costs.session(session.id)
    assert summary["by_stage"]["decision"]["usd"] == 0.00005 and summary["ended"] is None
    await session.stop_saving()


async def test_a_suspended_session_keeps_its_costs_across_a_restart(sessions, session):
    await session.add_cost("fact-finding B", "perplexity", "google/gemini-3.8-flash", 0.0081, own_usd=0.00812)
    session.recording_stopped_at = 1_790_000_000.0
    again = restore(sessions, json.loads(json.dumps(snapshot(session))), time.time())
    assert again.spend.event() == session.spend.event()
    assert again.cost_summary()["recording_stopped"] == "recording stopped and deleted at 17:13"


# --- The last session's line -------------------------------------------------------------------------------


async def test_hello_carries_the_last_sessions_line(unlocked, stt, store, config):
    ws = await connect(unlocked)
    await ws.close()
    hello_ws = await unlocked.ws_connect("/api/ws")
    assert (await hello_ws.receive_json(timeout=1))["costs"]["last_session"] is None
    await hello_ws.close()
    ws = await connect(unlocked)
    session_id = (await start(ws, record=False))["session"]
    await asyncio.sleep(0.05)
    await ws.send_json({"type": "end"})
    ended = (await receive(ws, "ended"))["summary"]
    ws = await unlocked.ws_connect("/api/ws")
    last = (await ws.receive_json(timeout=1))["costs"]["last_session"]
    summary = json.loads(await store.get(session_key(session_id)))
    assert last == {"started": summary["started"], "timezone": "Europe/Helsinki",
                    "listening_s": summary["listening_s"],
                    "cost_eur": round(ended["cost_usd"] / config.currency.ecb_usd_per_eur, 4),
                    "eur_per_hour": None}  # under a minute: no €/h
    assert last["listening_s"] == pytest.approx(ended["listening_s"], abs=0.2)
    # A new instance reads it from the store.
    fresh = Costs(store, quick(config))
    assert await fresh.last_session() == last
    assert unlocked.server.app[SESSIONS].costs is not fresh


async def test_the_last_sessions_line_has_its_rate_per_hour(store, config):
    costs = Costs(store, config)
    await costs.set_last_session({"session": "x", "started": "2026-09-27T18:02:11.000Z",
                                  "timezone": "Europe/Helsinki", "listening_s": 5400.0, "usd": 0.53})
    last = await Costs(store, config).last_session()
    rate = config.currency.ecb_usd_per_eur
    assert last == {"started": "2026-09-27T18:02:11.000Z", "timezone": "Europe/Helsinki", "listening_s": 5400.0,
                    "cost_eur": round(0.53 / rate, 4), "eur_per_hour": round(0.53 / rate / 1.5, 4)}


async def test_the_ended_summary_carries_the_start_screens_new_line(unlocked, stt):
    from .test_session import connect, receive, start

    ws = await connect(unlocked)
    await start(ws, record=False)
    await ws.send_json({"type": "end"})
    last = (await receive(ws, "ended"))["summary"]["last_session"]
    assert last is not None and {"started", "timezone", "listening_s", "cost_eur"} <= set(last)
