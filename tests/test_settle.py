"""Step 6: the settle call, the drop rule, the cap, the candidate timeout and
repeats of failed candidates."""

import asyncio
import dataclasses
import json
import logging
import time

import pytest

from carl import settle
from carl.checks import Checker
from carl.decision import Decider
from carl.location import Locator, Nominatim, Place
from carl.models import CallRecord, ModelError, TypedAnswer
from carl.server import SESSIONS
from carl.session import Card, Marker
from carl.settle import Settler, live_line, settle_outcome

from carl.prompts import load_prompts
from carl.session import Session, Sessions

from .conftest import ROOT
from .test_checks import (
    FI_CARD, SUPPORTED, FakeFinder, FakeLink, FakeTyped, check, flag, olympics, plug, reply, say, until,
)
from .test_decision import Events
from .test_decision import FakeModel as DecisionModel
from .test_session import connect, events, receive, start

LUNA_USD = 0.0000412


@pytest.fixture
def prompts():
    return load_prompts(ROOT / "prompts")


@pytest.fixture
def sessions(config, prompts, store, stt):
    return Sessions(config, prompts, store, stt, "test")


@pytest.fixture
def session(sessions):
    session = Session(sessions, "20260927T180000Z-abcdef", record=True, timezone="Europe/Helsinki")
    session.recorder = Events()
    session.link = FakeLink()
    return session


def settle_record(question, **changes) -> CallRecord:
    call = CallRecord("settle", "openai", "gpt-6-luna", question.prompt, question.version, dict(question.fields),
                      {"reasoning_effort": "none"}, input_tokens=380, cached_tokens=0, output_tokens=6,
                      cost_usd=LUNA_USD, elapsed_s=0.8, request={"input": "the rendered prompt"},
                      response={"output": []}, status=200)
    return dataclasses.replace(call, **changes)


class SettleModel:
    """The decision model answering settle calls: `(answer, probs)` replies
    in order, a typed error's kind, or a function of the question returning
    one; `none` when none are left."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.questions = []

    async def ask(self, question, *, stage):
        assert stage == "settle"
        self.questions.append(question)
        answer = self.replies.pop(0) if self.replies else ("none", {"none": 1.0})
        if callable(answer):
            answer = answer(question)
        if isinstance(answer, str):
            raise ModelError(answer, settle_record(question, error=answer, estimated=True, response=None,
                                                   status=None))
        choice, probs = answer
        assert choice in question.choices, (choice, list(question.choices))
        return TypedAnswer(choice, probs, settle_record(question))


def settles(cid, p=0.9):
    return f"settles {cid}", {f"settles {cid}": p, "none": 1 - p}


def candidate_in(session, state, text="Joo, vuonna 1956.", ago=5.0, fact=None):
    """A candidate in `state`, with a card when it has one."""
    candidate = flag(session, say(session, text, ago=ago))
    candidate.state = state
    if state in ("ready", "on screen", "card history", "withdrawn"):
        card_state = state
        session.cards[candidate.id] = Card(candidate.id, {"id": candidate.id, "fact": fact or f"{candidate.id} fact"},
                                           candidate.heard.time, candidate, card_state)
    return candidate


async def settle_on(sessions, session, text, *replies, ago=0.5, speaker="2"):
    model = SettleModel(*replies)
    heard = say(session, text, ago=ago, speaker=speaker)
    await Settler(sessions, model).on_utterance(session, heard)
    return model, heard


# --- The outcome ------------------------------------------------------------------------------


CHOICES = ["settles C1", "settles C2", "agrees with C3", "disputes C3", "none"]


@pytest.mark.parametrize("answer, probs, expected", [
    ("settles C1", {"settles C1": 0.8, "none": 0.2}, ("settles C1", 0.8)),
    ("settles C1", {"settles C1": 0.5, "none": 0.5}, ("settles C1", 0.5)),
    ("settles C1", {"settles C1": 0.45, "none": 0.3, "settles C2": 0.25}, ("none", 0.3)),
    ("none", {"none": 0.4, "disputes C3": 0.6}, ("disputes C3", 0.6)),
    ("none", {"none": 0.4, "settles *": 0.6}, ("none", 0.4)),  # names no candidate
    ("agrees with C3", None, ("agrees with C3", None)),
    ("none", None, ("none", None)),
])
def test_a_choice_counts_from_the_settle_threshold(config, answer, probs, expected):
    assert config.decision.settle_threshold == 0.5
    assert settle_outcome(answer, probs, CHOICES, config.decision.settle_threshold) == expected


# --- What the call is given -------------------------------------------------------------------


async def test_the_call_lists_only_the_live_candidates_with_their_choices(sessions, session):
    sessions.locator = Locator(sessions.config.location, Nominatim())
    session.place = Place("Kallio", "Helsinki", "Uusimaa", "Suomi / Finland", "FI")
    finding = candidate_in(session, "finding", "Joo, vuonna 1956.", ago=40)
    candidate_in(session, "silent", "Einstein reputti matikan.", ago=35)
    ready = candidate_in(session, "ready", "Eiffel-torni on 200 metriä.", ago=30)
    ready.restatement = "Eiffel-torni on 200 metriä korkea."
    on_screen = candidate_in(session, "on screen", "Kuka näytteli Rickiä?", ago=25,
                             fact="Todennäköisesti: Rickiä näytteli Humphrey Bogart.")
    for state in ("card history", "failed", "dropped", "recorded"):
        candidate_in(session, state, f"Jotain {state}.", ago=20)
    checking = candidate_in(session, "checking", "Suomessa on kaksi miljoonaa järveä.", ago=15)
    session.heard.append(Marker("paused", time.time() - 10))
    model, heard = await settle_on(sessions, session, "Ei vaan 1952, nyt muistan.")
    [question] = model.questions
    assert question.prompt == "settle" and question.version == sessions.prompts["settle"].version
    assert list(question.choices) == ["settles C1", "settles C3", "settles C9", "agrees with C4", "disputes C4",
                                      "none"]
    assert question.fields["live_candidates"] == "\n".join([
        "C1: Joo, vuonna 1956.", "C3: Eiffel-torni on 200 metriä korkea.",
        "C4: Kuka näytteli Rickiä? [on screen: Todennäköisesti: Rickiä näytteli Humphrey Bogart.]",
        "C9: Suomessa on kaksi miljoonaa järveä."])
    assert question.fields["utterance"] == "A2: Ei vaan 1952, nyt muistan."
    assert question.fields["conversation"].splitlines()[-2:] == ["A1: Suomessa on kaksi miljoonaa järveä.",
                                                                "(paused)"]
    assert question.fields["date_time"].endswith("(Europe/Helsinki)")
    assert "Kallio" not in json.dumps(question.fields, ensure_ascii=False)  # the date and time only
    assert live_line(finding) == "C1: Joo, vuonna 1956." and on_screen.live and checking.live


async def test_no_live_candidate_means_no_call(sessions, session):
    for state in ("silent", "card history", "failed", "dropped", "recorded"):
        candidate_in(session, state)
    model, _ = await settle_on(sessions, session, "Ei vaan 1952.")
    assert model.questions == [] and session.recorder.events == [
        e for e in session.recorder.events if e["event"] == "candidate"]


async def test_a_backchannel_utterance_gets_no_call(sessions, session):
    candidate_in(session, "finding")
    model, _ = await settle_on(sessions, session, "Joo joo.")
    assert model.questions == []


async def test_a_candidate_from_the_same_or_a_later_utterance_isnt_listed(sessions, session):
    earlier = candidate_in(session, "finding", ago=5)
    heard = say(session, "Ei vaan 1952.", ago=2)
    own = flag(session, heard)
    own.state = "finding"
    later = flag(session, say(session, "Eiffel-torni on 200 metriä.", ago=1))
    later.state = "finding"
    model = SettleModel()
    await Settler(sessions, model).on_utterance(session, heard)
    assert list(model.questions[0].choices) == [f"settles {earlier.id}", "none"]


async def test_the_call_waits_for_the_decisions_on_earlier_utterances(sessions, session):
    """A candidate flagged two seconds earlier, its decision still running, isn't missed."""
    release, found = asyncio.Event(), asyncio.Event()

    async def slow(question):
        await release.wait()
        return "claim", {"claim": 1.0}

    async def searching(request):
        await found.wait()
        return reply("claim is right")

    sessions.decider = Decider(sessions, DecisionModel(slow, ("none", {"none": 1.0})))
    sessions.checker = Checker(sessions, {"B": FakeFinder(searching)}, FakeTyped())
    model = SettleModel(settles("C1"))
    sessions.settler = Settler(sessions, model)
    sessions.on_utterance(session, say(session, "Joo, vuonna 1956.", ago=2))
    sessions.on_utterance(session, say(session, "Ei kun 1952 se oli.", ago=0.5))
    for _ in range(20):
        await asyncio.sleep(0)
    assert model.questions == [] and session.candidates == []  # still waiting for U1's decision
    release.set()
    await until(lambda: model.questions)
    assert list(model.questions[0].choices) == ["settles C1", "none"]
    await until(lambda: session.candidates[0].state == "dropped")
    found.set()
    while session.checks:
        await asyncio.wait(set(session.checks))
    assert session.candidates[0].state == "dropped"


# --- What a settle does ----------------------------------------------------------------------------


async def test_a_settle_drops_a_candidate_still_being_checked(sessions, session):
    candidate = olympics(session)
    found = asyncio.Event()

    async def searching(request):
        await found.wait()
        return reply("claim is wrong", FI_CARD)

    sessions.checker = Checker(sessions, {"B": FakeFinder(searching)}, FakeTyped(SUPPORTED))
    task = sessions.checker.start(session, candidate)
    await until(lambda: candidate.state == "finding" and candidate.waiting_on)
    _, heard = await settle_on(sessions, session, "Ei vaan, se oli 1952.", settles("C1"), speaker="2")
    assert candidate.state == "dropped"
    found.set()
    await task
    while session.checks:
        await asyncio.wait(set(session.checks))
    assert candidate.state == "dropped" and session.cards == {} and session.link.sent == []
    bands = session.recorder.of("band")
    assert bands == [{"event": "band", "candidate": "C1", "band": "none", "reason": "silent:settled", "shown": None,
                      "settled_by": heard.id}]  # the check's own band is thrown away
    [end] = session.recorder.of("check")
    assert (end["state"], end["reason"], end["settled_by"]) == ("dropped", "silent:settled", heard.id)
    assert session.recorder.of("finding")  # the finding still recorded…
    assert (await sessions.costs.month())["by_stage"]["fact-finding B"] > 0  # …and charged
    assert session.recorder.of("verdict") == []  # nothing more asked
    [settled] = session.recorder.of("settle")
    assert (settled["outcome"], settled["candidate"], settled["applied"]) == ("settles C1", "C1", True)


async def test_a_settle_withdraws_a_card_not_yet_shown(sessions, session):
    candidate = olympics(session)
    sessions.checker = await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)),
                                   FakeTyped(SUPPORTED))
    assert candidate.state == "ready"
    await settle_on(sessions, session, "Ei kun 1952.", settles("C1"))
    assert candidate.state == "dropped" and session.cards["C1"].state == "withdrawn"
    assert session.link.sent[-1] == {"type": "card_withdrawn", "id": "C1"}
    assert session.recorder.of("card withdrawn")[0]["reason"] == "silent:settled"
    message = session.cards_message()
    assert message["current"] is None and message["waiting"] == [] and message["history"] == []
    session.card_reported("shown", "C1", "2026-09-27T18:04:36.100Z")  # the page had already shown it
    assert session.cards["C1"].state == "withdrawn" and candidate.state == "dropped"


async def test_a_card_on_screen_is_never_withdrawn(sessions, session):
    on_screen = candidate_in(session, "on screen", fact="Todennäköisesti: 1952.")
    model, _ = await settle_on(sessions, session, "Ei kun 1952.")
    assert "settles C1" not in model.questions[0].choices
    sessions.checker = Checker(sessions, {"B": FakeFinder()}, FakeTyped())
    assert await sessions.checker.drop(session, on_screen, "silent:settled") is False
    assert on_screen.state == "on screen" and session.cards["C1"].state == "on screen"


async def test_a_settle_arriving_after_the_card_went_on_screen_changes_nothing(sessions, session):
    ready = candidate_in(session, "ready")
    sessions.checker = Checker(sessions, {"B": FakeFinder()}, FakeTyped())

    def shown_meanwhile(question):
        session.card_reported("shown", "C1", "2026-09-27T18:04:36.100Z")
        return settles("C1")

    await settle_on(sessions, session, "Ei kun 1952.", shown_meanwhile)
    assert ready.state == "on screen" and session.cards["C1"].state == "on screen" and session.link.sent == []
    assert session.recorder.of("settle")[0]["applied"] is False


async def test_the_card_history_never_changes(sessions, session):
    filed = candidate_in(session, "card history")
    model, _ = await settle_on(sessions, session, "Ei kun 1952.")
    assert model.questions == [] and filed.state == "card history" and session.cards["C1"].state == "card history"


async def test_agrees_is_recorded_and_shows_nothing(sessions, session):
    on_screen = candidate_in(session, "on screen")
    await settle_on(sessions, session, "Aivan, 1952 se oli.", ("agrees with C1", {"agrees with C1": 0.9}))
    assert on_screen.state == "on screen" and session.link.sent == []
    assert session.recorder.of("settle")[0] | {"probs": 0} == {
        "event": "settle", "utterance": "U2", "answer": "agrees with C1", "probs": 0, "outcome": "agrees with C1",
        "probability": 0.9, "candidate": "C1", "applied": False}


async def test_a_disputing_utterance_isnt_checked_separately(sessions, session):
    on_screen = candidate_in(session, "on screen")
    sessions.checker = Checker(sessions, {"B": FakeFinder()}, FakeTyped())
    _, heard = await settle_on(sessions, session, "Ei pidä paikkaansa, se oli 1956.",
                               ("disputes C1", {"disputes C1": 0.8, "none": 0.2}))
    assert on_screen.state == "on screen" and session.disputing == {heard.id: "C1"}
    flagged = flag(session, heard)  # the decision on it comes back after the settle call
    assert sessions.checker.start(session, flagged) is None
    assert flagged.state == "dropped"
    assert session.recorder.of("check")[-1] | {"after_s": 0} == {
        "event": "check", "candidate": "C2", "state": "dropped", "after_s": 0, "reason": "silent:disputing",
        "disputes": "C1"}


async def test_a_candidate_already_flagged_in_the_disputing_utterance_is_dropped(sessions, session):
    candidate_in(session, "on screen")
    heard = say(session, "Ei pidä paikkaansa, se oli 1956.", ago=0.5)
    flagged = flag(session, heard)
    flagged.state = "finding"
    sessions.checker = Checker(sessions, {"B": FakeFinder()}, FakeTyped())
    await Settler(sessions, SettleModel(("disputes C1", {"disputes C1": 0.8}))).on_utterance(session, heard)
    assert flagged.state == "dropped" and session.recorder.of("band")[-1]["reason"] == "silent:disputing"


async def test_a_settle_call_is_recorded_and_charged(sessions, session):
    candidate_in(session, "finding")
    await settle_on(sessions, session, "Ei kun 1952.")
    [call] = session.recorder.of("model call")
    assert call["stage"] == "settle" and call["prompt"] == "settle" and call["utterance"] == "U2"
    assert call["choices"] == ["settles C1", "none"] and "request" not in call
    month = await sessions.costs.month()
    assert month["by_stage"] == {"settle": pytest.approx(LUNA_USD)} and session.cost_usd == pytest.approx(LUNA_USD)
    assert session.recorder.of("settle")[0]["outcome"] == "none"


async def test_a_failed_settle_call_is_a_failure_and_changes_nothing(sessions, session, caplog):
    candidate = candidate_in(session, "finding")
    with caplog.at_level(logging.WARNING, logger="carl.settle"):
        await settle_on(sessions, session, "Ei kun 1952.", "timeout")
    assert candidate.state == "finding"
    assert session.recorder.of("failure") == [{"event": "failure", "stage": "settle", "kind": "timeout",
                                               "provider": "openai", "model": "gpt-6-luna", "status": None,
                                               "code": None, "candidate": None}]
    assert session.recorder.of("settle") == [{"event": "settle", "utterance": "U2", "outcome": "failed",
                                              "error": "timeout"}]
    assert (await sessions.costs.month())["estimated_usd"] == pytest.approx(LUNA_USD)


def test_the_settle_call_uses_the_decision_model(sessions):
    settle.install(sessions)
    assert sessions.settler is None  # no decision call, no settle call
    sessions.decider = Decider(sessions, DecisionModel())
    settle.install(sessions)
    assert sessions.settler.model is sessions.decider.model


# --- The cap and the timeout --------------------------------------------------------------------------


async def test_beyond_the_cap_a_new_candidate_fails_with_overload(sessions, session):
    assert sessions.config.candidates.max_live == 8
    for state in ("finding", "checking", "ready", "on screen", "finding", "checking", "finding", "finding"):
        candidate_in(session, state)
    candidate_in(session, "silent")  # not live
    ninth = flag(session, say(session, "Eiffel-torni on 200 metriä."))
    finder = FakeFinder()
    assert Checker(sessions, {"B": finder}, FakeTyped()).start(session, ninth) is None
    assert ninth.state == "failed" and finder.requests == []
    assert session.recorder.of("failure") == [{"event": "failure", "stage": "fact-finding", "kind": "overload",
                                               "provider": None, "model": None, "status": None, "code": None,
                                               "candidate": ninth.id, "live": 8}]
    assert session.recorder.of("check")[-1]["kind"] == "overload"


@pytest.fixture
def short_timeout(sessions):
    candidates = dataclasses.replace(sessions.config.candidates, timeout_s=2.3)  # the utterance ended 2 s ago
    sessions.config = dataclasses.replace(sessions.config, candidates=candidates)


async def test_a_candidate_stuck_finding_times_out(sessions, session, short_timeout):
    async def slow(request):
        await asyncio.sleep(0.6)
        return reply("claim is wrong", FI_CARD)

    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(slow), FakeTyped(SUPPORTED))
    assert candidate.state == "failed" and session.cards == {} and session.link.sent == []
    assert session.recorder.of("failure") == [{"event": "failure", "stage": "fact-finding B", "kind": "timeout",
                                               "provider": "perplexity", "model": "google/gemini-3.8-flash",
                                               "status": None, "code": None, "candidate": "C1"}]
    [end] = session.recorder.of("check")
    assert (end["state"], end["stage"], end["kind"], end["waiting_on"]) == (
        "failed", "fact-finding", "timeout", ["fact-finding B"])
    assert session.recorder.of("finding") and session.recorder.of("band") == []  # recorded, thrown away


async def test_a_candidate_stuck_checking_times_out_against_fact_checking(sessions, session, short_timeout):
    class Slow(FakeTyped):
        async def ask(self, question, *, stage):
            await asyncio.sleep(0.6)
            return await super().ask(question, stage=stage)

    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), Slow(SUPPORTED))
    assert candidate.state == "failed" and session.cards == {}
    assert [(f["stage"], f["kind"]) for f in session.recorder.of("failure")] == [("fact-checking", "timeout")]
    assert session.recorder.of("check")[0]["stage"] == "fact-checking"
    assert session.recorder.of("verdict")  # the verdict still recorded, and thrown away
    assert session.recorder.of("band") == []


async def test_a_ready_card_doesnt_time_out(sessions, session, short_timeout):
    candidate = olympics(session)
    await check(sessions, session, candidate, FakeFinder(reply("claim is wrong", FI_CARD)), FakeTyped(SUPPORTED))
    await asyncio.sleep(0.5)
    assert candidate.state == "ready" and session.recorder.of("failure") == []


# --- Repeats of failed candidates ------------------------------------------------------------------------


@pytest.mark.parametrize("state, checked", [("failed", True), ("silent", False), ("ready", False),
                                            ("card history", False), ("finding", False), ("dropped", False)])
async def test_a_repeat_of_a_failed_candidate_is_checked_as_a_new_one(sessions, session, state, checked):
    earlier = candidate_in(session, state, ago=30)
    sessions.checker = Checker(sessions, {"B": FakeFinder(reply("claim is right"))}, FakeTyped())
    probs = {"same as C1": 0.9, "claim": 0.1}
    decider = Decider(sessions, DecisionModel(("same as C1", probs)))
    await decider.on_utterance(session, say(session, "Se oli kyllä 1956, olen varma."))
    assert len(session.candidates) == 1 + checked
    assert session.recorder.of("repeat")[-1] == {"event": "repeat", "utterance": "U2", "candidate": "C1",
                                                 "probability": 0.9}
    if checked:
        repeat = session.candidates[1]
        assert (repeat.id, repeat.kind, repeat.repeat_of, repeat.state) == ("C2", earlier.kind, "C1", "finding")
        assert session.recorder.of("candidate")[-1]["repeat_of"] == "C1"
        assert session.recorder.of("decision")[-1] | {"probs": 0} == {
            "event": "decision", "utterance": "U2", "outcome": "repeat of failed", "candidate": "C2",
            "repeat_of": "C1", "answer": "same as C1", "probs": 0}
        while session.checks:
            await asyncio.wait(set(session.checks))
        assert repeat.state == "silent"
    else:
        assert session.recorder.of("decision")[-1]["outcome"] == "repeat"


async def test_a_repeat_of_an_overloaded_candidate_is_checked_later(sessions, session):
    for _ in range(8):
        candidate_in(session, "finding")
    ninth = flag(session, say(session, "Eiffel-torni on 200 metriä."))
    checker = sessions.checker = Checker(sessions, {"B": FakeFinder(reply("claim is right"))}, FakeTyped())
    checker.start(session, ninth)
    session.candidates[0].state = "silent"  # one finished meanwhile
    decider = Decider(sessions, DecisionModel(("same as C9", {"same as C9": 0.95})))
    await decider.on_utterance(session, say(session, "Eiffel-torni on kaksisataa metriä korkea."))
    assert session.candidates[-1].repeat_of == "C9" and session.candidates[-1].state == "finding"


# --- Through the WebSocket --------------------------------------------------------------------------------


async def test_a_card_settled_before_it_was_shown_is_withdrawn_on_the_page(unlocked, stt, store, prompts):
    sessions = plug(unlocked, prompts, FakeFinder(reply("claim is wrong", FI_CARD)))

    def corrects(question):
        return settles("C1") if "1952" in question.fields["utterance"] else ("none", {"none": 1.0})

    sessions.settler = Settler(sessions, SettleModel(corrects, corrects, corrects))
    ws = await connect(unlocked)
    session_id = (await start(ws))["session"]
    stt.streams[0].say("1", "Joo, vuonna 1956.")
    card = (await receive(ws, "card"))["card"]
    stt.streams[0].say("1", "Ei kun 1952 se oli.", start_ms=3000)
    assert await receive(ws, "card_withdrawn") == {"type": "card_withdrawn", "id": card["id"]}
    session = unlocked.server.app[SESSIONS].get(session_id)
    assert session.candidates[0].state == "dropped"
    await ws.close()
    ws = await connect(unlocked)
    await ws.send_json({"type": "rejoin", "session": session_id})
    await receive(ws, "session")
    await ws.send_json({"type": "end"})
    ended = await receive(ws, "ended")  # no `cards` in between: nothing is left on the screen
    assert ended["summary"]["cards"] == 0
    log = await events(store, session_id)
    assert [e["reason"] for e in log if e["event"] == "band"] == ["hedged:single-verified", "silent:settled"]
    assert [e["id"] for e in log if e["event"] == "card withdrawn"] == ["C1"]
